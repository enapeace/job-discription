
## 기획

### 목표

점프잇(사람인) 채용 공고를 수집·정제·청킹·임베딩해 PostgreSQL(pgvector)에 적재하고, 사용자 질의에 대해 **RAG + Tool calling**으로 답변하는 파이프라인.

- **데이터**: 크롤링 → cleaning → nomalizing → chunking(상위·하위 유지) → embedding
- **저장**: jobs / chunks 테이블 (pgvector HNSW 인덱스)
- **서비스**: 질의 임베딩 → 벡터 검색 top_k → LLM(gpt-4o-mini)에 컨텍스트 + 필요 시 툴(get_job_detail, get_jobs_title_link, get_job_descriptions) 호출 → 한국어 답변

### 실행 요약

- **ETL**: 크롤링 → cleaning → nomalizing → chunking → embedding → load (각 단계 스크립트 실행)
- **질의**: `uv run src/generation/ask.py` — 터미널에서 질문 입력 후 답변·사용 툴·검색 청크 로그 확인


### 프로젝트 구조

```
job-discription/
├── data/                      # 단계별 데이터
│   ├── crawling/              # jobs_YYYYMMDD_HHMM.json
│   ├── cleaning/              # cleaning_YYYYMMDD_HHMM.json
│   ├── nomalizing/            # nomalizing_YYYYMMDD_HHMM.json
│   ├── chunking/              # chunking_YYYYMMDD_HHMM.json
│   └── embedding/             # embedding_YYYYMMDD_HHMM.jsonl
├── docs/                      # PIPELINE_PLAN.md, README 등
├── src/
│   ├── db/                    # DB 인프라·연결
│   │   ├── conn.py            # PostgreSQL 연결 (get_conn)
│   │   └── docker-compose.yml
│   ├── etl/                   # ETL 파이프라인 (수집·정제·청킹·임베딩·적재)
│   │   ├── crawling.py
│   │   ├── cleaning.py
│   │   ├── nomalizing.py
│   │   ├── chunking.py
│   │   ├── embedding.py
│   │   └── load.py
│   ├── retrieval/             # 검색 (질의 임베딩·벡터 검색)
│   │   └── retriever.py
│   └── generation/            # RAG + Tool calling
│       ├── ask.py
│       ├── llm.py
│       └── tool.py
├── requirements.txt
└── .env
```
---

# 1. RAW INPUT (크롤링 데이터)

| 필드 | 소스 | 예시 |
|------|------|------|
| `title` | 점프잇 크롤링 | "[AI] 3D Vision Researcher (신입)" |
| `href` / `job_info_url` | 점프잇 크롤링 | "/position/52895679" / "https://jumpit.saramin.co.kr/position/52895679" |
| `job_category` | 점프잇 크롤링 | "인공지능/머신러닝" |
| `company_name`, `company_url`, `company_tags` | 점프잇 크롤링 | 회사명, 회사 페이지 URL, ["태그1", "태그2"] |
| `requirements` | 점프잇 크롤링 | 경력, 학력, 마감일, 근무지역 (키) |
| `job_description` | 점프잇 크롤링 | 기술스택, 주요업무, 자격요건, 우대사항, 복지 및 혜택, 채용절차 및 기타 지원 유의사항 (키) |
| `company_info` | 점프잇 크롤링 | 전체_직원수, 평균_연봉, 매출액, 영업이익 (키) |

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
- **숫자+괄호** `1) `, `2) ` → 상위로 쓰이는 경우가 있음 (이때 하위는 `-` 로 표현되기도 함)
- 단, 일부 채용 공고에서는 `■`가 상위, `·`가 하위로 불릿 계층이 표현될 수 있음  
- 불릿 계층 부호별 상하위 구조 예시:

| 상위 불릿 | 하위 불릿 | 계층 설명              |
|:---------:|:--------:|:----------------------|
| -         | ·        | -가 상위, ·가 하위     |
| ■         | ·        | ■가 상위, ·가 하위     |
| 1), 2), … | -        | 숫자괄호가 상위, -가 하위 |

- `-`, `■`, `·`, `1)` 등을 서로 통일하지 않음


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


## 3.2 위치

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

#### Step 3: location_detail›
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

상·하위 표현은 두 가지 스타일을 지원한다.

| 스타일 | 상위 | 하위 |
|--------|------|------|
| 불릿 스타일 | `-`, `■` | `·` |
| 숫자 스타일 | `1)`, `2)`, `3)` … | `-` |

- **불릿 스타일**: `-`/`■`로 시작하는 줄 = 상위 → 그 아래 `·` 줄들을 하위로 한 chunk에 포함.
- **숫자 스타일**: `1)`, `2)` 등으로 시작하는 줄 = 상위 → 그 아래 `-`로 시작하는 줄들을 하위로 한 chunk에 포함.
- chunk_text 생성 시 상·하위 부호(`-`, `■`, `·`, `1)` 등)는 제거하고 `[chunk_type] -상위:하위1, 하위2` 형식으로 변환.

### main_tasks (주요 업무)
- 상위(`-`/`■` 또는 `1)`/`2)`…) = 1 chunk의 기준
- 해당 상위 아래의 **하위 항목**(`·` 또는 숫자 스타일일 때 `-`)을 함께 포함
- chunk_text: 부호 제거 후 `[주요 업무] -상위:하위1, 하위2, 하위3` 형식으로 변환. 
- `·`만 있는 필드값인 경우 그냥 `·` 제거.

**예:** `[주요 업무] -Imitation Learning 연구:Demonstration 기반 학습, Offline RL 최적화`

### skills (기술스택)
- chunk_text: `[기술 스택] -기술1, 기술2, 기술3`

### requirements (자격요건), preferred (우대사항)
| 상황 | 전략 |
|------|------|
| 계층 없음 | bullet 1줄 = 1 chunk |
| 계층 있음 (불릿: `-`/`■` + `·`) | 상위 기준으로 묶기, chunk_text에 상위:하위 형식 적용 |
| 계층 있음 (숫자: `1)`/`2)` + `-`) | 상위(`1)`, `2)`…) 기준으로 묶기, 하위(`-`) 포함해 chunk_text에 상위:하위 형식 적용 |

## 4.3 금지 사항

- `·` → `-` 변환 금지
- 계층 제거 금지
- 상위/하위를 분리해 따로 chunk 생성 금지
- 문단 합치기 금지

## 4.4 chunk_text와 임베딩/검색

- **`글자•글자` 유지**: `머신러닝•딥러닝`처럼 `•`가 단어 사이(공백 없음)에 있는 경우는 **삭제하지 않는다**. 목록 불릿(`• ` 뒤에 공백 있는 경우)만 제거한다.
- **임베딩·검색**: `머신러닝•딥러닝`과 `머신러닝과 딥러닝`은 둘 다 “머신러닝 + 딥러닝”이라는 같은 의미라서, 임베딩 벡터가 가깝게 나오는 경우가 많다. 따라서 질문이 *머신러닝과 딥러닝을 사용하는 공고를 찾아줘*처럼 자연어여도, 청크에 `머신러닝•딥러닝`만 있어도 의미가 통하므로 검색이 잘 되는 편이다.

---

# 출력 예시

## cleaning_YYYYMMDD_HHMM.json (1건)

```json
{
  "job_post_id": "52895679",
  "job_category": "인공지능/머신러닝",
  "post_title": "[로봇/AI] 3D Vision Researcher (신입)",
    "job_description": {
      "기술스택": "C++, Python",
      "주요업무": "1) 3D Showroom 핵심 CV/3D Vision 문제 연구\n- 이미지 기반 실내 공간에서의 3D 재구성 품질 향상 연구\n- SfM/MVS/NeRF/Gaussian Splatting 등 차세대 3D 표현/복원 기술 적용 및 개선\n- 공간의 구조적 일관성을 유지하는 geometry/texture optimization 연구\n\n2) 공간 이해(Spatial Understanding) 및 고수준 인식\n- 객체 인식·세그멘테이션(가구/문/창/계단/조명 등) 기반 쇼룸 자동 태깅\n\n3) 실사용 환경 Robust CV\n- 저조도, 반사(거울/유리), 반복 패턴, 단색 벽 등 Hard case 대응\n- 동적 객체(사람/반려동물) 제거 및 정적 공간 복원 기술 연구\n\n4) 연구 성과의 제품화(Productionization)\n- SLAM/3D 파이프라인과 결합해 실시간·후처리 하이브리드 구조 설계\n- 모바일/엣지 환경에서의 경량화 및 실시간 추론 최적화\n- 제품 팀과의 요구 정렬, PRD 리뷰, 릴리즈 성과 분석 및 반복 개선",
      "자격요건": "1) Computer Vision / 3D Vision / ML 분야 연구 또는 실무 1년 이상 (이에 준하는 박사 연구 경력)\n2) CV/3D 핵심 주제 중 1개 이상 깊이 있는 경험\n- 3D Reconstruction / MVS / NeRF / Gaussian Splatting\n- Depth/Normal/Surface 추정\n- Semantic/Instance Segmentation\n- Indoor scene understanding / layout estimation\n3) PyTorch/TensorFlow 등 딥러닝 프레임워크 기반 연구 구현 능력\n4) 논문/오픈소스 리딩 및 재현·개선 능력\n5) 실험 설계→학습→평가→개선의 Research loop을 독립적으로 운용할 수 있는 역량\n6) 실제 서비스/제품 문제를 연구적 언어로 치환하고 현실 제약 속에서 해법을 찾는 능력/경험",
      "우대사항": "1) 모바일/실환경에서의 3D CV 제품화 경험 (ARKit/ARCore, on-device inference)\n2) NeRF/3DGS 계열 최신 연구 경험 또는 논문 게재\n3) CVPR/ECCV/ICCV/NeurIPS/ICRA/IROS 등 Top-tier 논문 게재 경험\n4) 글로벌/대규모 데이터셋 구축 및 domain generalization 경험\n\n※ 우대사항은 필수 요건이 아닙니다.",
      "코딩테스트 여부": "채용 절차에 코딩테스트 없음"
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
  "chunk_text": "주요 업무에는 3D Showroom 핵심 CV/3D Vision 문제 연구가 있으며, 자세한 내용으로는 이미지 기반 실내 공간 3D 재구성 품질 향상, SfM/MVS/NeRF/Gaussian Splatting 적용 및 개선 등이 있다.",
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

### 상위·하위 의미를 유지한 청킹 출력 예시

위 cleaning 예시의 `job_description.주요업무`는 **1) ~ 4)** 상위와 **-** 하위로 계층이 나뉘어 있음. 청킹 시 **상위 하나 + 그 아래 하위 항목들**을 한 chunk로 묶어, `chunk_text`에 “상위가 있으며, 자세한 내용은 하위1, 하위2, … 등이 있다” 형식으로 넣음.

**원문(주요업무 일부):**
```
1) 3D Showroom 핵심 CV/3D Vision 문제 연구
- 이미지 기반 실내 공간에서의 3D 재구성 품질 향상 연구
- SfM/MVS/NeRF/Gaussian Splatting 등 차세대 3D 표현/복원 기술 적용 및 개선
- 공간의 구조적 일관성을 유지하는 geometry/texture optimization 연구

2) 공간 이해(Spatial Understanding) 및 고수준 인식
- 객체 인식·세그멘테이션(가구/문/창/계단/조명 등) 기반 쇼룸 자동 태깅
```

**청킹 결과(동일 공고에서 나온 chunk 일부):**

| chunk_id   | chunk_type | chunk_text (상위·하위 유지) |
|------------|------------|-----------------------------|
| 52895679_1 | 기술스택   | 기술스택은 C++, Python이다. |
| 52895679_2 | 주요 업무  | 주요 업무에는 3D Showroom 핵심 CV/3D Vision 문제 연구가 있으며, 자세한 내용은 이미지 기반 실내 공간에서의 3D 재구성 품질 향상 연구, SfM/MVS/NeRF/Gaussian Splatting 등 차세대 3D 표현/복원 기술 적용 및 개선, 공간의 구조적 일관성을 유지하는 geometry/texture optimization 연구 등이 있다. |
| 52895679_3 | 주요 업무  | 주요 업무에는 공간 이해(Spatial Understanding) 및 고수준 인식이 있으며, 자세한 내용은 객체 인식·세그멘테이션(가구/문/창/계단/조명 등) 기반 쇼룸 자동 태깅 등이 있다. |
| …          | 자격요건 / 우대사항 | 동일하게 **상위 기준 1 chunk**, 그 하위 항목들을 한 문장으로 이어서 저장 |

- **상위**: `1)`, `2)` 또는 `-`, `■`로 시작하는 줄이 하나의 chunk 단위.
- **하위**: 해당 상위 아래의 `-`(숫자 스타일일 때) 또는 `·` 항목들이 그 chunk의 “자세한 내용”으로 함께 포함됨.
- 계층을 나누지 않고, 상위/하위를 한 덩어리로 유지해 검색·답변 시 문맥이 깨지지 않도록 함.

---


# 5. EMBEDDING

**입력**: `data/chunking/chunking_*.json` — 각 레코드의 `chunk_text`
**출력**: 각 chunk에 `embedding` 벡터 추가 → `data/embedding/embedding_*.jsonl` (또는 `.json`)

**구현**: `src/etl/embedding.py`

## 5.1 모델

| 항목 | 값 |
|------|-----|
| API | OpenAI API |
| 모델 | `text-embedding-3-small` |
| 차원 | 1536 |
| 대상 필드 | `chunk_text` |
| 배치 크기 | 100 |

## 5.2 처리 흐름

```
chunking_*.json
     ↓
chunk_text 추출
     ↓
OpenAI Embeddings API 호출 (text-embedding-3-small, 비동기 배치 처리)
     ↓
배치마다 즉시 JSONL 한 줄씩 기록 (중간 실패 시 그때까지 결과 보존)
     ↓
data/embedding/embedding_*.jsonl (1줄 = 레코드 1개, embedding 필드 포함)
```

- JSON 배열 형식(`embedding_*.json`)으로 저장된 파일도 LOAD 단계에서 지원됨.

---

# 6. LOAD

**구현**: `src/etl/load.py`

- **DB**: PostgreSQL + pgvector 확장
- **환경변수**: `DATABASE_URL` 또는 `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`

## 6.1 테이블

| 테이블 | 입력 파일 | 설명 |
|--------|-----------|------|
| **jobs** | `data/nomalizing/nomalizing_*.json` | 공고 정규화 데이터. `job_post_id`, `post_title`, `job_post_url`, `requirements`, `job_description`, `company`, `experience_*`, `location_*` 등 |
| **chunks** | `data/embedding/embedding_*.jsonl` 또는 `embedding_*.json` | 청크 + 임베딩. `chunk_id`, `chunk_type`, `chunk_text`, `embedding`(vector 1536), `job_post_id`, `job_category`, `post_title`, `job_post_url` |

- chunks 테이블: `embedding` 컬럼에 HNSW 인덱스(코사인 유사도) 생성.

---

# 7. AUGMENTED GENERATION

**구현**: `src/generation/llm.py`, `src/retrieval/retriever.py`, `src/generation/tool.py`, `src/generation/ask.py`

## 7.1 흐름

1. **검색(Retriever)**  
   사용자 질의 → 쿼리 임베딩(`text-embedding-3-small`) → chunks 테이블 코사인 유사도 벡터 검색 → **top_k(기본 10)개 청크** 반환.
2. **컨텍스트 구성**  
   검색된 청크(공고ID, 제목, 청크 타입, chunk_text, 유사도)를 문자열로 이어 붙여 LLM 유저 메시지에 포함.
3. **LLM 호출**  
   OpenAI `gpt-4o-mini` + Tool calling. 필요 시 툴 호출 후 결과를 컨텍스트에 추가해 재호출.

## 7.2 모델

| 항목 | 값 |
|------|-----|
| LLM | OpenAI `gpt-4o-mini` |
| 쿼리 임베딩 | `text-embedding-3-small` (retriever) |
| top_k | 10 (기본) |

## 7.3 Tools (SQL/DB 조회)

| 툴 이름 | 용도 | 반환 |
|---------|------|------|
| **get_job_detail** | 특정 공고의 상세 정보(회사, 복지, 채용 절차, 경력, 근무지 등)가 필요할 때 | `job_post_id`, `post_title`, `job_post_url`, `company`, `requirements`, `job_description`, `hiring_process`, `experience_*`, `location_*` 등 |
| **get_jobs_title_link** | 추천 공고를 제목·링크로 정리해 보여줄 때 | `job_post_id` 목록에 대한 `post_title`, `job_post_url` 목록 |
| **get_job_descriptions** | 직무·업무·역할·담당업무 관련 질문에 답할 때 | 검색된 청크 공고 n개(기본 5, 최대 10)의 `job_description`(직무소개) |

- LLM이 판단해 위 툴을 호출하며, 툴 결과를 참고해 최종 답변 생성.
- 실행: `uv run src/generation/ask.py` — 터미널에서 질의 입력 후 RAG 답변·툴 호출 로그 확인 가능.

---

# 응답 화면
<img width="408" height="362" alt="Image" src="https://github.com/user-attachments/assets/b96d4f76-1bb8-4d92-b7b1-d928fe4dca1c" />

<img width="381" height="137" alt="Image" src="https://github.com/user-attachments/assets/b20f77a0-32d1-4287-8f41-307b8f93b2d0" />

<img width="404" height="210" alt="Image" src="https://github.com/user-attachments/assets/aa3ce39d-221d-4e92-a7f0-9f2e25c85b2b" />

<img width="398" height="197" alt="Image" src="https://github.com/user-attachments/assets/6d3bf4cb-ab74-4c31-bc12-239e34ec7269" />


## tool 콜링 화면 
<img width="483" height="205" alt="Image" src="https://github.com/user-attachments/assets/16b6e7be-8de5-4fe4-bc71-4876278cc69a" />

<img width="430" height="173" alt="Image" src="https://github.com/user-attachments/assets/1cda0c29-eea1-4f6b-b95d-ad107a894668" />

<img width="359" height="329" alt="Image" src="https://github.com/user-attachments/assets/82c2fa5f-d94a-465e-87ff-5cafd16e6539" />

---

# 추후 개선점

- **청크 길이**: 지금 단계에서는 청크를 합치지 않고 두고, 검색/답 품질을 보면서 필요해지면 그때 합치는 쪽이 부담이 적다. 개선 시에는 “최소 길이(토큰/문자) 미만이면 다음 청크와 합치기” 같은 규칙을 도입하는 방안을 고려할 수 있다.

- **LnagGraph**: “검색 → 요약 → 검증 → 재검색” 같은 다단계·분기·루프가 생기면 그때 LangGraph로 구현
