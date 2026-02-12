# 채용공고 데이터 노말라이징 계획

> **데이터 소스**: `data/crawling/jobs_20260212_1839.json`  
> **목적**: 벡터 검색 + 정확 필터 질의를 위한 구조화·표준화

---

## 데이터 현황 요약

| 필드 | 소스 경로 | 예시 값 | 비고 |
|------|-----------|---------|------|
| 기술스택 | `job_description.기술스택` | "C++, Python", "AI/인공지능, SQL, Tableau" | 쉼표 구분, 혼합 표기 |
| 주요업무/자격/우대 | `job_description.주요업무/자격요건/우대사항` | 긴 텍스트 블록 | 시그널 추출 대상 |
| 경력 | `requirements.경력` | "신입", "경력 1~15년", "경력 2~20년" | enum 매핑 필요(신입,3년,5년,10년 이상) |
| 학력 | `requirements.학력` | "대학교졸업(4년) 이상", "무관", "석사졸업 이상" | enum 매핑 필요(무관, 4년제 대학졸업 이상, (2년제)대학졸업이상 석사졸업 이상, 박사졸업이상) |
| 근무지역 | `requirements.근무지역` | "서울 구로구 디지털로285, 210호" | 시·구·상세 분리 필요 |

---

## 1) 기술스택 정규화 (1순위)

### 대상
- `job_description.기술스택` 문자열

### 목적
- "React 있는 JD", "Spring+Java", "AI 코딩도구 경험" 같은 질의는 벡터보다 **정확 필터**가 필요

### 정규화 결과 스키마
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `stack_raw` | string | 원문 그대로 보관 |
| `stack` | text[] | 정규화된 토큰 목록 |


### 정규화 룰

#### Step 1: 토큰화
- 구분자: `,` `/` `·` ` `(공백 연속)
- 예: `"C++, Python"` → `["C++", "Python"]`
- 예: `"AI/인공지능, SQL"` → `["AI/인공지능", "SQL"]`

#### Step 2: 정규화
- **소문자화**: 모든 토큰 → 소문자
- **공백/불필요 기호 제거**: 앞뒤 공백, 연속 공백


#### Step 3: stack_family 매핑 (선택)
| stack 토큰 예시 | stack_family |
|-----------------|--------------|
| python, java, c++, go, node.js | backend |
| react, vue, javascript, typescript, html5, css3 | frontend |
| docker, kubernetes, aws, gcp, azure, linux | devops |
| pytorch, tensorflow, ai, deep_learning, ml | ai |
| postgresql, mysql, mongodb, redis | database |

### 구현 순서
1. `split` + 정규식으로 토큰 추출
2. 동의어 딕셔너리 기반 치환
3. 중복 제거 후 배열로 저장

---

## 2) 요구 경험/업무 “시그널 태그” (2순위)

### 대상
- `job_description.주요업무` + `job_description.자격요건` + `job_description.우대사항` 합친 텍스트

### 목적
- "데이터 파이프라인", "클라우드 운영" 등 표현 다양 → **표준 태그**로 검색·분석

### 정규화 결과 스키마
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `signals` | jsonb / list | 추출된 시그널 태그 목록 |
| (선택) `signals_with_evidence` | jsonb | `{태그: "근거 문장"}` 형태 (LLM 보정 시) |

### 시그널 태그 목록 (예시)
| 그룹 | 태그 예시 |
|------|-----------|
| 데이터 | `data_pipeline`, `etl`, `warehouse`, `streaming` |
| 인프라 | `cloud_ops`, `deployment`, `monitoring` |
| ML/AI | `ml_training`, `ml_serving`, `mlops` |
| 기타 | `gis`, `bigdata`, `si_project`, `maintenance` |

### 추출 방식

#### 1차: 키워드/정규식 (일관성 우선)
| 키워드 패턴 (예) | 매핑 태그 |
|------------------|-----------|
| 데이터 파이프라인, data pipeline | `data_pipeline` |
| ETL, etl | `etl` |
| 웨어하우스, warehouse | `warehouse` |
| 스트리밍, streaming | `streaming` |
| 클라우드 운영, AWS, GCP, Azure | `cloud_ops` |
| 배포, deployment, CI/CD | `deployment` |
| 모니터링, monitoring | `monitoring` |
| ML ops, MLOps, LLMOps | `mlops` |
| 모델 학습, 파인튜닝 | `ml_training` |
| RAG, 벡터 DB | `ml_serving` |
| GIS, 지리정보 | `gis` |
| 빅데이터, bigdata | `bigdata` |
| SI, 유지보수 | `si_project`, `maintenance` |

#### 2차: LLM 분류 (보정)
- 1차에서 매칭 안 된 문장만 LLM에 전달
- "이 문장에서 요구하는 경험/업무 태그를 골라라" + 근거 문장 포함

### 구현 순서
1. 주요업무/자격요건/우대사항 텍스트 합치기
2. 정규식/키워드 매칭 테이블 기반 추출
3. (선택) 매칭 실패 구간만 LLM API 호출

---

## 3) 경력/학력/고용조건 (3순위)

### 대상
- `requirements.경력`
- `requirements.학력`

### 목적
- "신입만", "1~2년", "학력 조건"은 **의미검색이 아니라 정확 조건 필터**

### 정규화 결과 스키마
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `experience_raw` | string | 경력 원문 |
| `experience_min_years` | int | 최소 경력 연수 (신입=0) |
| `experience_max_years` | int \| null | 최대 경력 연수 (상한 없으면 null) |
| `education_raw` | string | 학력 원문 |
| `education_level` | enum | HIGH_SCHOOL, COLLEGE, BACHELOR, MASTER, DOCTORATE, UNSPECIFIED |

### 경력 파싱 룰
| 원문 패턴 | experience_min | experience_max |
|-----------|----------------|----------------|
| 신입 | 0 | 0 |
| 경력 1~15년 | 1 | 15 |
| 경력 2~20년 | 2 | 20 |
| 경력 3~8년 | 3 | 8 |
| 경력 4~7년 | 4 | 7 |
| 경력 1~3년 | 1 | 3 |
| 경력 8~15년 | 8 | 15 |
| 경력 3~20년 | 3 | 20 |
| 경력 3~15년 | 3 | 15 |

- 정규식: `경력\s*(\d+)~?(\d*)년` 또는 `신입`

### 학력 파싱 룰
| 원문 패턴 | education_level |
|-----------|-----------------|
| 고등학교졸업 이상 | HIGH_SCHOOL |
| 대학졸업(2,3년) 이상 | COLLEGE |
| 대학교졸업(4년) 이상 | BACHELOR |
| 석사졸업 이상 | MASTER |
| 박사졸업 이상 | DOCTORATE |
| 무관 | UNSPECIFIED |

### 구현 순서
1. 정규식으로 경력 숫자 추출
2. "신입" 문자열 체크 → 0, 0
3. 학력 키워드 매칭 → enum 매핑

---

## 4) 위치 (4순위)

### 대상
- `requirements.근무지역`

### 목적
- "마포구", "서울 서부권" 같은 **지역 필터** 질의 대응

### 정규화 결과 스키마
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `location_raw` | string | 원문 |
| `location_city` | string | 시/도 (서울, 경기, 부산, 세종 등) |
| `location_district` | string | 구/시/군 (마포구, 강남구 등) |
| `location_detail` | string (선택) | 상세 주소 (디지털로285, 210호 등) |

### 파싱 룰
| 원문 예시 | city | district | detail |
|-----------|------|----------|--------|
| 서울 구로구 디지털로285, 210호 | 서울 | 구로구 | 디지털로285, 210호 |
| 서울 강남구 선릉로525, 3층 | 서울 | 강남구 | 선릉로525, 3층 |
| 경기 안양시 동안구 시민대로327번길28, 5,6층 | 경기 | 안양시 동안구 | 시민대로327번길28, 5,6층 |
| 부산 남구 전포대로133, 14층 116호 | 부산 | 남구 | 전포대로133, 14층 116호 |
| 세종 나성로125-4, 314호 | 세종 | - | 나성로125-4, 314호 |

- 정규식: `^(서울|경기|부산|대구|인천|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)\s*(.+)$`
- 두 번째 캡처그룹에서 "구", "시", "군" 포함 여부로 district 추출
- 나머지는 detail (도로명+상세)

### 구현 순서
1. 시/도 목록으로 시작 토큰 매칭
2. 그 다음 구/시/군 패턴 매칭
3. 남은 부분을 detail로 저장
4. (선택) 지오코딩은 나중에 필요 시만

---

## 출력 형식

노말라이징 완료 후 JSON 구조 예시:

```json
{
  "no": 1,
  "title": "[로봇/AI] 3D Vision Researcher (신입)",
  "job_info_url": "...",
  "job_category": "인공지능/머신러닝",
  "company_name": "세코어로보틱스",
  "job_description": { ... },
  "requirements": { ... },
  "company_info": { ... },
  "normalized": {
    "stack_raw": "C++, Python",
    "stack": ["c++", "python"],
    "stack_family": ["backend"],
    "signals": ["ml_training", "cloud_ops"],
    "experience_raw": "신입",
    "experience_min_years": 0,
    "experience_max_years": 0,
    "education_raw": "대학교졸업(4년) 이상",
    "education_level": "BACHELOR",
    "location_raw": "서울 구로구 디지털로285, 210호",
    "location_city": "서울",
    "location_district": "구로구",
    "location_detail": "디지털로285, 210호"
  }
}
```

- 기존 필드는 유지하고, `normalized` 객체를 추가하는 방식 권장

---

## 구현 우선순위

| 순위 | 항목 | 복잡도 | 의존성 |
|------|------|--------|--------|
| 1 | 기술스택 | 중 | 없음 |
| 2 | 시그널 태그 | 중~고 | 1차: 키워드만으로 가능 |
| 3 | 경력/학력 | 하 | 없음 |
| 4 | 위치 | 중 | 시/도·구 목록 필요 |

---

## 다음 단계

1. **OK 확인** 후 `src/retrieval/nomalizing.py`에 구현
2. `data/normalized/jobs_normalized_YYYYMMDD_HHMM.json` 형태로 출력
3. 필요 시 각 정규화 모듈을 함수로 분리해 테스트 가능하게 구성
