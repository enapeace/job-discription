# R (Retrieval) — 정보 검색·조회

> **Retrieval**: 외부에서 정보를 검색·조회  
> 질의에 맞는 JD(채용공고)를 검색할 수 있도록 데이터를 준비하고 저장하는 파트입니다.

---

## 1. 데이터 수집

- 크롤링
- Playwright

### 크롤링 완료된 데이터 예시

```json
{
  "no": 1,
  "title": "B2B 프로젝트 개발팀 신입",
  "job_info_url": "https://jumpit.saramin.co.kr/position/52883932",
  "href": "/position/52883932",
  "job_category": "인공지능/머신러닝",
  "company_name": "에스피에이치",
  "company_url": "https://jumpit.saramin.co.kr/company/MTA3ODcyMTA3OA==?company_nm=에스피에이치",
  "company_tags": ["연봉상승률 15% 이상", "휴가비 지원", "5호선 역세권 기업", "평균연봉 6,000 이상"],
  "requirements": {
    "경력": "신입",
    "학력": "대학교졸업(4년) 이상",
    "마감일": "2026-02-19",
    "근무지역": "서울 마포구 마포대로92, A동 3층"
  },
  "job_description": {
    "기술스택": "Git, Java, React, Spring, AI/인공지능",
    "주요업무": "...",
    "자격요건": "...",
    "우대사항": "...",
    "복지 및 혜택": "..."
  },
  "company_info": {
    "전체_직원수": "??명",
    "평균_연봉": "",
    "매출액": "",
    "영업이익": ""
  }
}
```

- `company_info`는 로그인을 해야 볼 수 있음.

---

## 2. Normalizing

- JD는 **의미 보존**을 전제로 자연어 형태로 변환할 수 있으나, 정보 삭제나 추론적 재작성은 금지한다.

---

## 3. Cleaning

- (추가 규칙 작성)

---

## 4. Chunking

- JD는 템플릿·추상 표현·중복 키워드가 많아 그대로 벡터화하면 구분력이 떨어진다.
- 반드시 **'주요 업무·요구 기술·우대 사항·기술 스택·경력 조건'** 같은 의미 단위로 청킹해야 한다.

---

## 5. Embedding

- OpenAI API, `text-*-small` 모델 사용

---

## 6. Load (벡터 스토어 저장)

- JD 인사이트를 얻으려면 **회사명·직무 카테고리·경력 여부·회사 규모** 같은 메타데이터를 반드시 함께 저장해야 한다.
- **PostgreSQL** 사용
- 기본 스키마: 청킹번호, embedding, 회사명, 직무 카테고리, 경력여부, 회사 규모
