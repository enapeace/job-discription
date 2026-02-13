# ETL 파이프라인 계획

> **데이터 소스**: `data/crawling/jobs_YYYYMMDD_HHMM.json`  
> **출력**: `data/cleaning/cleaning_YYYYMMDD_HHMM.json` → `data/chunking/chunking_YYYYMMDD_HHMM.json`

---

## 전체 흐름

```
Crawling JSON
     ↓
┌─────────────────────────────────────────────────────────────┐
│  1. CLEANING (노이즈 제거, 의미 보존)                          │
│     - HTML 엔티티, 줄바꿈, 공백 정리                           │
│     - ⚠ 불릿 계층(-/·) 절대 통일 금지                          │
└─────────────────────────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────────────────────────┐
│  2. NORMALIZING (구조화·표준화)                               │
│     - 경력(원문·min·max), 위치(시/도·구군·상세) → normalized (7개 필드) │
└─────────────────────────────────────────────────────────────┘
     ↓
┌─────────────────────────────────────────────────────────────┐
│  3. CHUNKING (계층 고려 청킹)                                 │
│     - 상위(-) 기준 chunk, 하위(·) 포함                         │
│     - 임베딩용 chunk_text 생성                                 │
└─────────────────────────────────────────────────────────────┘
     ↓
Embedding → Load
```

---

# 1. RAW INPUT (크롤링 데이터)

| 필드 | 소스 | 예시 |
|------|------|------|
| `title` | - | "[AI] 3D Vision Researcher (신입)" |
| `href` / `job_info_url` | - | "/position/52895679" 또는 "https://jumpit.saramin.co.kr/position/52895679" |
| `job_category` | - | "인공지능/머신러닝" |
| `company_name`, `company_url`, `company_tags` | - | - |
| `requirements` | - | 경력, 학력, 마감일, 근무지역 |
| `job_description` | - | 기술스택, 주요업무, 자격요건, 우대사항, 복지 및 혜택, 채용절차 및 기타 지원 유의사항 |
| `company_info` | - | 전체_직원수, 평균_연봉, 매출액, 영업이익 |

---

# 2. CLEANING

**출력 파일**: `data/cleaning/cleaning_YYYYMMDD_HHMM.json`

## 2.1 Cleaning 출력 스키마

### job_post_id
- **추출**: `href` 또는 `job_info_url`에서 `/position/` 뒤 숫자만 추출
- **예**: `https://jumpit.saramin.co.kr/position/52895679` → `52895679`

### job_category
- **소스**: `job_category` 그대로

### post_title
- **소스**: `title` 그대로

### job_description (벡터디비 대상 필드)
세부 필드를 **합치지 않고** 객체 형태로 유지. (기술스택, 주요업무, 자격요건, 우대사항, 채용절차 및 기타 지원 유의사항)  
`복지 및 혜택`은 `company`로 이동.

예시 구조: 각 필드를 별도로 보관 (합치지 않음).
```json
"job_description": {
  "기술스택": "C++, Python",
  "주요업무": "...",
  "자격요건": "...",
  "우대사항": "...",
  "채용절차 및 기타 지원 유의사항": "..."
}
```

**특수 규칙**: `채용절차 및 기타 지원 유의사항` 내용에 `코딩테스트`가 포함되어 있으면 → `코딩테스트 있음`을 삽입

### hiring_process
- **소스**: `채용절차 및 기타 지원 유의사항` 전체 내용
- **처리**: 앞에 `채용 절차 및 지원 시 유의사항은 ` 붙이기

### company
`company_*` / `company_info` 필드로 구성:
| 필드 | 소스 |
|------|------|
| company_name | company_name |
| company_url | company_url |
| company_tags | company_tags |
| 전체_직원수 | company_info.전체_직원수 |
| 평균_연봉 | company_info.평균_연봉 |
| 매출액 | company_info.매출액 |
| 영업이익 | company_info.영업이익 |
| 복지 및 혜택 | job_description.복지 및 혜택 |

## 2.2 Cleaning 시 텍스트 정리

### 2.2.1 필수 클리닝

| 항목 | 전략 | 대상 필드 |
|------|------|-----------|
| HTML 엔티티 | `html.unescape()`, `&amp;amp;` → `&` | 전체 텍스트 |
| 줄바꿈 | `\r\n` → `\n`, `\n{3,}` → `\n\n` | job_description.* |
| 중복 공백 | 2개 이상 공백 → 1개 | 전체 |
| 앞뒤 공백 | `strip()` | 전체 문자열 |
| 이모지 | 제거 | 전체 |
| 빈 문자열 | `""` → `null` | company_info 등 |
| 전각 기호 | `＞` → `>` (선택) | 채용절차 화살표 등 |


### 2.2.2 불릿 계층 보존 ⚠
- `- ` 또는 `■` → 상위 개념 (level 1) **유지**
- `· ` → 하위 개념 (level 2) **유지**
- 단, 일부 채용 공고에서는 `■`가 상위, `·`가 하위로 불릿 계층이 표현될 수 있음  
- 불릿 계층 부호별 상하위 구조 예시:

| 상위 불릿 | 하위 불릿 | 계층 설명          |
|:---------:|:--------:|:------------------|
| -         | ·        | -가 상위, ·가 하위 |
| ■         | ·        | ■가 상위, ·가 하위 |

- `-`, `■`, `·`를 서로 통일하지 않음


---

# 3. NORMALIZING

**목적**: 경력·지역 필터 적용을 위한 구조화·표준화  
**입력**: Cleaning 출력 또는 Raw의 `requirements` (경력, 근무지역)  
**출력**: `normalized` 객체 — **7개 필드** (experience_raw, experience_min_years, experience_max_years, location_raw, location_city, location_district, location_detail)

---

## 3.1 경력

### 목적
- "신입만", "1~2년", "학력 무관" 등 **조건 필터**
- 숫자/범위 기반 필터링

### 대상
- `requirements.경력`
- `requirements.학력`

### 출력
- `experience_raw`: 경력 원문
- `experience_min_years`: int (신입=0)
- `experience_max_years`: int \| null (상한 없으면 null)


### 경력 처리 절차

#### Step 1: "신입" 여부 확인
- 원문에 `신입` 포함 → `experience_min_years=0`, `experience_max_years=0`

#### Step 2: 숫자 범위 파싱
- **정규식**: `경력\s*(\d+)~(\d+)년` 또는 `경력\s*(\d+)\s*년`
- 예: `경력 1~15년` → min=1, max=15
- 예: `경력 2~20년` → min=2, max=20
- 예: `경력 3~8년` → min=3, max=8
- 예: `경력 4~7년` → min=4, max=7
- 예: `경력 8~15년` → min=8, max=15
- 예: `경력 11~15년` → min=11, max=15
- 예: `경력 5~13년` → min=5, max=13
- 상한만 있는 경우 (예: `경력 3년 이상`) → min=3, max=null

#### 파싱 실패 시
- `experience_min_years=null`, `experience_max_years=null`


## 3.2 위치 (필수)

### 목적
- "마포구", "서울 서부권" 등 **지역 필터**

### 대상
- `requirements.근무지역`

### 출력
- `location_raw`: 원문 그대로
- `location_city`: 시/도 (서울, 경기, 부산 등)
- `location_district`: 구/시/군 (마포구, 강남구, 안양시 동안구 등)
- `location_detail`: 도로명·상세 주소

### 처리 절차
#### Step 1: 시/도 추출
- **시/도 목록**: 서울, 경기, 부산, 대구, 인천, 광주, 대전, 울산, 세종, 강원, 충북, 충남, 전북, 전남, 경북, 경남, 제주
- 원문 앞부분에서 매칭 (예: `서울시` → `서울`)
- 정규식: `^(서울시?|경기|부산|대구|인천|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)\s*`

#### Step 2: 구/시/군 추출
- 시/도 다음 토큰에서 `구`, `시`, `군` 포함 여부 확인
- 예: `서울 구로구` → district=`구로구`
- 예: `경기 안양시 동안구` → district=`안양시 동안구`
- 예: `부산 남구` → district=`남구`
- 예: `대전 유성구` → district=`유성구`
- 예: `세종` → district=`""` (세종시는 구 단위 없음)

#### Step 3: location_detail
- 시/도, 구/시/군을 제외한 나머지 (도로명, 건물명, 호수 등)
- 예: `디지털로285, 210호`, `선릉로525, 3층`

#### 예시
| 원문 | location_city | location_district | location_detail |
|------|---------------|-------------------|-----------------|
| 서울 구로구 디지털로285, 210호 | 서울 | 구로구 | 디지털로285, 210호 |
| 서울 강남구 선릉로525, 3층 | 서울 | 강남구 | 선릉로525, 3층 |
| 경기 안양시 동안구 시민대로327번길28, 5,6층 | 경기 | 안양시 동안구 | 시민대로327번길28, 5,6층 |
| 부산 남구 전포대로133, 14층 116호 | 부산 | 남구 | 전포대로133, 14층 116호 |
| 세종 나성로125-4, 314호 | 세종 | (빈 문자열) | 나성로125-4, 314호 |
| 서울시 성동구 성수일로10 서울숲ITCT 1602호 | 서울 | 성동구 | 성수일로10 서울숲ITCT 1602호 |
| 대전 유성구 유성대로1689번길70 | 대전 | 유성구 | 유성대로1689번길70 |

---

## 3.4 출력 통합

Normalizing 결과는 Cleaning/Chunking 단계의 각 레코드에 `normalized` 객체로 추가한다.  
**normalized는 아래 7개 필드만 포함한다.**

| 필드 | 설명 |
|------|------|
| experience_raw | 경력 원문 |
| experience_min_years | 경력 최소 연수 (신입=0) |
| experience_max_years | 경력 최대 연수 (상한 없으면 null) |
| location_raw | 근무지역 원문 |
| location_city | 시/도 |
| location_district | 구/시/군 |
| location_detail | 도로명·상세 주소 |

```json
"normalized": {
  "experience_raw": "신입",
  "experience_min_years": 0,
  "experience_max_years": 0,
  "location_raw": "서울 구로구 디지털로285, 210호",
  "location_city": "서울",
  "location_district": "구로구",
  "location_detail": "디지털로285, 210호"
}
```

---




# 4. CHUNKING

**입력**: `cleaning_YYYYMMDD_HHMM.json`  
**출력**: `data/chunking/chunking_YYYYMMDD_HHMM.json`

## 4.1 Chunking 출력 스키마 (필수 필드만)

청킹 결과는 **아래 7개 필드만** 포함한다.

| 필드 | 설명 |
|------|------|
| job_post_id | Cleaning에서 전달 |
| job_category | Cleaning에서 전달 |
| post_title | **title 필드값** 그대로 |
| chunk_type | 기술스택 / 주요 업무 / 자격요건 / 우대사항 |
| chunk_id | job_post_id + index 로 생성 (예: `52895679_0`) |
| chunk_text | `[chunk_type] -상위:하위, 하위` 형식 |

### chunk_type
| 값 | 한글 |
|----|------|
| skills | 기술스택 |
| main_tasks | 주요 업무 |
| requirements | 자격요건 |
| preferred | 우대사항 |

### chunk_text 형식
- **형식**: `[chunk_type] -상위:하위, 하위`
- **예**: `[skills] -Python:Django, JavaScript`
- **예**: `[주요 업무] -Imitation Learning 연구:Demonstration 기반 학습, Offline RL 최적화`


## 4.2 청킹 규칙 (계층 고려)

### main_tasks (주요 업무)
- `-`로 시작하는 줄 = **상위 개념** → 1 chunk의 기준
- 해당 상위 아래의 **모든 `·` 하위 항목**을 함께 포함
- chunk_text: `-`, `■`, `·`를 제거하되 `[주요 업무] -상위:하위1, 하위2, 하위3` 형식으로 변환. 
- `·`만 있는 필드값인 경우 그냥 `·`제거.

**예:** `[주요 업무] -Imitation Learning 연구:Demonstration 기반 학습, Offline RL 최적화`

### skills (기술스택)
- chunk_text: `[기술 스택] -기술1, 기술2, 기술3`

### requirements (자격요건), preferred (우대사항)
| 상황 | 전략 |
|------|------|
| 계층 없음 | bullet 1줄 = 1 chunk |
| 계층 있음 (`-` + `·`) | 상위(`-`) 기준으로 묶기, chunk_text에 상위:하위 형식 적용 |

## 4.3 금지 사항

- `·` → `-` 변환 금지
- 계층 제거 금지
- 상위/하위를 분리해 따로 chunk 생성 금지
- 문단 합치기 금지

---

# 4. 출력 예시

## cleaning_YYYYMMDD_HHMM.json (1건)

```json
{
  "job_post_id": "52895679",
  "job_category": "인공지능/머신러닝",
  "post_title": "[로봇/AI] 3D Vision Researcher (신입)",
  "job_description": {
    "기술스택": "C++, Python",
    "주요업무": "...",
    "자격요건": "...",
    "우대사항": "...",
    "채용절차 및 기타 지원 유의사항": "..."
  },
  "requirements": {
      "경력": "신입",
      "학력": "대학교졸업(4년) 이상",
      "마감일": "2026-02-20",
      "근무지역": "서울 구로구 디지털로285, 210호"
    },
  "hiring_process": "채용 절차 및 지원 시 유의사항은 서류전형 - 1차 면접...",
  "company": {
    "company_name": "세코어로보틱스",
    "company_url": "https://...",
    "company_tags": ["2호선 역세권 기업", "유연근무제", "점심지원"],
    "전체_직원수": "16명",
    "평균_연봉": "4,081만원",
    "매출액": "3,000만원",
    "영업이익": "-12억 8,665만원",
    "복지 및 혜택": "세코어로보틱스는..."
  }
}
```

## chunking_YYYYMMDD_HHMM.json (1건)

```json
{
  "job_post_id": "52895679",
  "job_category": "인공지능/머신러닝",
  "post_title": "[로봇/AI] 3D Vision Researcher (신입)",
  "chunk_type": "주요 업무",
  "chunk_id": "52895679_0",
  "chunk_text": "[주요 업무] -3D Showroom 핵심 CV/3D Vision 문제 연구:이미지 기반 실내 공간 3D 재구성 품질 향상, SfM/MVS/NeRF/Gaussian Splatting 적용 및 개선",
  "metadata_dlfjscompany": {
    "company_name": "세코어로보틱스",
    "company_url": "https://...",
    "company_tags": ["2호선 역세권 기업", "유연근무제", "점심지원"],
    "전체_직원수": "16명",
    "평균_연봉": "4,081만원",
    "매출액": "3,000만원",
    "영업이익": "-12억 8,665만원",
    "복지 및 혜택": "세코어로보틱스는..."
  }
}
```

---

# 5. 구현 순서

| 단계 | 모듈 | 입력 | 출력 |
|------|------|------|------|
| 1 | Cleaning | `data/crawling/jobs_*.json` | `data/cleaning/cleaning_*.json` |
| 2 | Normalizing | Cleaning 출력 | `normalized` 객체 추가 |
| 3 | Chunking | `data/cleaning/cleaning_*.json` | `data/chunking/chunking_*.json` |
| 4 | Embedding | chunk_text | - |
| 5 | Load | embedding + metadata | Vector DB |

---

# 6. 참고 문서

- `cleaning-nomalizeing-chunking.md` — 불릿 계층·청킹 원칙
- `NORMALIZATION_PLAN.md` — (선택) 기술스택·시그널·경력·위치 정규화
- `README_R_Retrieval.md` — Retrieval 파이프라인 개요
