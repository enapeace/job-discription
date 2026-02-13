"""
NORMALIZING - 구조화·표준화

PIPELINE_PLAN.md 3. NORMALIZING 스펙 구현
- 기술스택: 토큰화, 정규화, 동의어 매핑 (주로 질의 정규화용)
- 경력/학력: 숫자 범위 파싱, enum 매핑
- 위치: 시/도, 구/시/군, 상세 주소 추출

참고: 공고 데이터의 기술스택은 이미 통일된 선택지에서 선택한 값이므로,
      정규화는 주로 사용자 질의를 검색하기 좋게 정제할 때 사용합니다.
      공고 데이터 정규화는 선택적으로 수행할 수 있습니다.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


# 동의어 매핑 (정규화용)
SYNONYM_MAP = {
    "javascript": {"x-javascript", "x_javascript", "javascript", "js"},  # js는 스택 토큰일 때만
    "ai": {"ai", "인공지능", "ai/인공지능"},
    "rest_api": {"restful api", "rest api", "restful-api", "rest-api"},
    "deep_learning": {"deep learning", "deeplearning", "deep-learning", "dl"},
    "machine_learning": {"machine learning", "machinelearning", "machine-learning", "ml"},
    "html5": {"html5", "html 5"},
    "css3": {"css3", "css 3"},
    "nlp": {"nlp", "npl"},  # 오타 보정
    "etl": {"etl"},
    "azure": {"azure", "azur"},  # 토큰 필드에만 권장
    # "c": {"c language", "c lang"}  # 'c' 단독 매핑은 피하고, 이 정도만 허용
}



def normalize_stack_token(token: str) -> str:
    """
    기술스택 토큰 정규화
    - 소문자화
    - 앞뒤 공백 제거
    - 연속 공백 제거
    - 동의어 매핑
    """
    if not token:
        return ""
    
    # 앞뒤 공백 제거
    token = token.strip()
    
    # 콜론 뒤 공백 정리
    token = re.sub(r":\s+", ": ", token)
    
    # 연속 공백 제거
    token = re.sub(r"\s+", " ", token)
    
    # 소문자화
    token_lower = token.lower()
    
    # 동의어 매핑: 정확 일치만 처리
    for normalized, variants in SYNONYM_MAP.items():
        for variant in variants:
            if token_lower == variant.lower():
                return normalized
    
    return token_lower


def normalize_stack(stack_raw: str) -> list[str]:
    """
    기술스택 정규화
    - 토큰화: , / · 공백 연속으로 분리
    - 각 토큰 정규화
    """
    if not stack_raw or not isinstance(stack_raw, str):
        return []
    
    # 구분자로 분리: , / · 공백 연속
    tokens = re.split(r"[,/·\s]+", stack_raw)
    
    # 각 토큰 정규화 및 필터링
    normalized = []
    for token in tokens:
        token = token.strip()
        if token:
            normalized_token = normalize_stack_token(token)
            if normalized_token and normalized_token not in normalized:
                normalized.append(normalized_token)
    
    return normalized


def parse_experience(experience_raw: str) -> tuple[int | None, int | None]:
    """
    경력 파싱
    Returns: (min_years, max_years)
    - 신입: (0, 0)
    - 범위: (min, max)
    - 상한만: (min, None)
    - 파싱 실패: (None, None)
    """
    if not experience_raw or not isinstance(experience_raw, str):
        return (None, None)
    
    # 신입 여부 확인
    if "신입" in experience_raw:
        return (0, 0)
    
    # 범위 파싱: 경력 1~15년, 경력 2~20년 등
    range_match = re.search(r"경력\s*(\d+)~(\d+)년", experience_raw)
    if range_match:
        min_years = int(range_match.group(1))
        max_years = int(range_match.group(2))
        return (min_years, max_years)
    
    # 단일 값: 경력 3년 이상
    single_match = re.search(r"경력\s*(\d+)\s*년", experience_raw)
    if single_match:
        min_years = int(single_match.group(1))
        return (min_years, None)
    
    return (None, None)


def parse_education(education_raw: str) -> str:
    """
    학력 enum 매핑
    Returns: HIGH_SCHOOL | COLLEGE | BACHELOR | MASTER | DOCTORATE | UNSPECIFIED
    """
    if not education_raw or not isinstance(education_raw, str):
        return "UNSPECIFIED"
    
    education_lower = education_raw.lower()
    
    # 매칭 순서: 높은 학력부터
    if "박사" in education_lower:
        return "DOCTORATE"
    elif "석사" in education_lower:
        return "MASTER"
    elif "대학교졸업(4년)" in education_raw or "학사" in education_lower:
        return "BACHELOR"
    elif "대학졸업(2,3년)" in education_raw or "전문학사" in education_lower:
        return "COLLEGE"
    elif "고등학교" in education_lower:
        return "HIGH_SCHOOL"
    elif "무관" in education_lower:
        return "UNSPECIFIED"
    
    return "UNSPECIFIED"


def parse_location(location_raw: str) -> tuple[str, str, str]:
    """
    위치 파싱
    Returns: (city, district, detail)
    """
    if not location_raw or not isinstance(location_raw, str):
        return ("", "", "")
    
    # 시/도 목록
    sido_pattern = r"^(서울시?|경기|부산|대구|인천|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)\s*"
    
    # 시/도 추출
    sido_match = re.match(sido_pattern, location_raw)
    if not sido_match:
        return ("", "", location_raw.strip())
    
    city = sido_match.group(1).replace("시", "").strip()
    remaining = location_raw[sido_match.end():].strip()
    
    # 구/시/군 추출
    district = ""
    detail = ""
    
    # 구/시/군 패턴: 다음 토큰에서 구, 시, 군 포함 여부 확인
    district_match = re.match(r"([^\s]+(?:구|시|군))", remaining)
    if district_match:
        district = district_match.group(1)
        detail = remaining[len(district):].strip()
    else:
        # 세종시는 구 단위 없음
        detail = remaining
    
    return (city, district, detail)


def normalize_query_stack(query: str) -> list[str]:
    """
    사용자 질의의 기술스택을 정규화하여 검색에 사용
    
    Args:
        query: 사용자가 입력한 기술스택 질의 (예: "React, Python", "Spring+Java")
    
    Returns:
        정규화된 기술스택 토큰 리스트
    
    Example:
        >>> normalize_query_stack("React, Python, DeepLearning")
        ['react', 'python', 'deep_learning']
        >>> normalize_query_stack("AI/인공지능")
        ['ai']
    """
    return normalize_stack(query)


def normalize_job(job: dict, normalize_stack_field: bool = False) -> dict:
    """
    Cleaning 출력 1건 → normalized 객체 (경력 3개 + 위치 4개 = 7개 필드)
    
    Args:
        job: Cleaning 단계 출력 레코드
        normalize_stack_field: 사용하지 않음 (하위 호환용 유지)
    
    Returns:
        normalized 객체: experience_raw, experience_min_years, experience_max_years,
                         location_raw, location_city, location_district, location_detail
    """
    requirements = job.get("requirements", {})
    
    # 경력
    experience_raw = requirements.get("경력", "") or ""
    experience_min_years, experience_max_years = parse_experience(experience_raw)
    
    # 위치
    location_raw = requirements.get("근무지역", "") or ""
    location_city, location_district, location_detail = parse_location(location_raw)
    
    return {
        "experience_raw": experience_raw,
        "experience_min_years": experience_min_years,
        "experience_max_years": experience_max_years,
        "location_raw": location_raw,
        "location_city": location_city,
        "location_district": location_district,
        "location_detail": location_detail,
    }


def run(
    input_path: str | Path,
    output_path: str | Path | None = None,
    normalize_stack_field: bool = False,
) -> Path:
    """
    Cleaning JSON 로드 → Normalizing 적용 → 저장
    
    Args:
        input_path: Cleaning 출력 JSON 경로
        output_path: 출력 파일 경로 (기본: 입력 파일과 동일 디렉터리, normalized_ 접두어)
        normalize_stack_field: 기술스택 필드를 정규화할지 여부 (기본: False)
                              공고 데이터는 이미 통일된 선택지이므로 기본적으로 False
                              검색 효율을 위해 정규화된 버전도 저장하고 싶을 때 True
    
    Returns:
        저장된 파일 경로
    """
    input_path = Path(input_path)
    
    if output_path is None:
        # nomalizing_YYYYMMDD_HHMM.json 형식으로 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        output_dir = Path("data/nomalizing")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"nomalizing_{timestamp}.json"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(input_path, "r", encoding="utf-8") as f:
        cleaned_jobs = json.load(f)
    
    # 각 레코드에 normalized 추가
    normalized_jobs = []
    for job in cleaned_jobs:
        normalized = normalize_job(job, normalize_stack_field=normalize_stack_field)
        job_with_normalized = {**job, "normalized": normalized}
        normalized_jobs.append(job_with_normalized)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(normalized_jobs, f, ensure_ascii=False, indent=2)
    
    return output_path


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        # 기본값: data/cleaning 디렉터리에서 가장 최근 cleaning 파일 찾기
        cleaning_files = sorted(Path("data/cleaning").glob("cleaning_*.json"))
        if not cleaning_files:
            print("에러: data/cleaning 디렉터리에 cleaning_*.json 파일이 없습니다.")
            print("사용법: python src/retrieval/nomalizing.py <input_file>")
            sys.exit(1)
        input_file = cleaning_files[-1]
        print(f"입력 파일을 찾았습니다: {input_file}")
    
    out = run(input_file)
    print(f"Normalizing 완료: {out}")
