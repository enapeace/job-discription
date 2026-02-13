"""
CLEANING - 크롤링 데이터 노이즈 제거, 구조 변환

PIPELINE_PLAN.md 2. CLEANING 스펙 구현
- job_post_id 추출, job_description 객체 유지, company 구성
- HTML 엔티티, 줄바꿈, 공백, 이모지 정리
- 불릿 계층(-, ■, ·) 유지 (통일 금지)
"""

import json
import re
from html import unescape
from pathlib import Path
from datetime import datetime
from typing import Any


# 이모지 제거용 정규식 (한글/한자 제외, emoji 전용 범위만)
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002602-\U000027B0"  # misc symbols (제한)
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "]+",
    flags=re.UNICODE,
)


def clean_text(text: str | None) -> str | None:
    """
    텍스트 클리닝: HTML 엔티티, 줄바꿈, 공백, 이모지
    불릿 계층(-, ■, ·)은 유지 (통일하지 않음)
    """
    if text is None or not isinstance(text, str):
        return None if text is None else text

    # HTML 엔티티 디코딩
    s = unescape(text)

    # 줄바꿈 정리
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)

    # 중복 공백 → 1개 (줄 내부만, 줄바꿈은 유지)
    s = re.sub(r"[^\S\n]+", " ", s)

    # 전각 기호 정리 (선택)
    s = s.replace("＞", ">")

    # 이모지 제거
    s = EMOJI_PATTERN.sub("", s)

    # 앞뒤 공백/줄바꿈 제거
    s = s.strip()

    return s if s else None


def empty_to_none(value: Any) -> Any:
    """빈 문자열 "" → None"""
    if value == "":
        return None
    return value


def extract_job_post_id(job: dict) -> str | None:
    """href 또는 job_info_url에서 /position/ 뒤 숫자 추출"""
    for key in ("href", "job_info_url"):
        val = job.get(key)
        if not val or not isinstance(val, str):
            continue
        m = re.search(r"/position/(\d+)", val)
        if m:
            return m.group(1)
    return None


def clean_job(raw: dict) -> dict:
    """
    Raw 크롤링 1건 → Cleaning 출력 스키마로 변환
    """
    job_desc = raw.get("job_description") or {}
    company_info = raw.get("company_info") or {}

    # 채용절차 원문
    hiring_raw = job_desc.get("채용절차 및 기타 지원 유의사항") or ""
    hiring_cleaned = clean_text(hiring_raw)
    if hiring_cleaned is None:
        hiring_cleaned = ""

    # 특수 규칙: 코딩테스트 여부 표시
    coding_test_status = (
        "채용 절차에 코딩테스트 있음"
        if ("코딩테스트" in (hiring_raw or "") or "코딩 테스트" in (hiring_raw or ""))
        else "채용 절차에 코딩테스트 없음"
    )

    # job_description: 세부 필드 별도 유지 (복지 및 혜택 제외)
    job_description = {
        "기술스택": clean_text(job_desc.get("기술스택")) or "",
        "주요업무": clean_text(job_desc.get("주요업무")) or "",
        "자격요건": clean_text(job_desc.get("자격요건")) or "",
        "우대사항": clean_text(job_desc.get("우대사항")) or "",
        "코딩테스트 여부": coding_test_status,
    }

    # company
    welfare = clean_text(job_desc.get("복지 및 혜택")) or ""
    company = {
        "company_name": empty_to_none(clean_text(raw.get("company_name"))) or "",
        "company_url": empty_to_none(raw.get("company_url")) or "",
        "company_tags": [
            clean_text(t) or t
            for t in (raw.get("company_tags") or [])
            if t
        ],
        "전체 직원수": empty_to_none(company_info.get("전체_직원수")) or "",
        "평균 연봉": empty_to_none(company_info.get("평균_연봉")) or "",
        "매출액": empty_to_none(company_info.get("매출액")) or "",
        "영업이익": empty_to_none(company_info.get("영업이익")) or "",
        "복지 및 혜택": welfare,
    }

    req = raw.get("requirements") or {}

    return {
        "job_post_id": extract_job_post_id(raw) or "",
        "job_post_url": raw.get("job_info_url") or "",
        "job_category": clean_text(raw.get("job_category")) or "",
        "post_title": clean_text(raw.get("title")) or "",
        "job_description": job_description,
        "hiring_process": hiring_cleaned,
        "requirements": {
            "경력": req.get("경력") or "",
            "학력": req.get("학력") or "",
            "마감일": req.get("마감일") or "",
            "근무지역": req.get("근무지역") or "",
        },
        "company": company,
    }


def run(
    input_path: str | Path,
    output_dir: str | Path | None = None,
) -> Path:
    """
    크롤링 JSON 로드 → Cleaning 적용 → 저장

    Args:
        input_path: 크롤링 결과 JSON 경로
        output_dir: 출력 디렉터리 (기본: data/cleaning)

    Returns:
        저장된 파일 경로
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir) if output_dir else Path("data/cleaning")
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(input_path, "r", encoding="utf-8") as f:
        raw_jobs = json.load(f)

    cleaned = [clean_job(j) for j in raw_jobs]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = output_dir / f"cleaning_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    return output_path


if __name__ == "__main__":
    import sys

    input_file = sys.argv[1] if len(sys.argv) > 1 else "data/crawling/jobs_20260212_1839.json"
    out = run(input_file)
    print(f"Cleaning 완료: {out}")
