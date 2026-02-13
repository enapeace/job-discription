"""
CHUNKING - 계층 고려 청킹

PIPELINE_PLAN.md 4. CHUNKING 스펙 구현
- cleaning JSON → chunk 리스트
- 상위(-/■) 기준 chunk, 하위(·) 포함
- chunk_text: [chunk_type] -상위:하위1, 하위2 형식
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator

# chunk_type 값 (한글)
CHUNK_TYPES = {
    "skills": "기술스택",
    "main_tasks": "주요 업무",
    "requirements": "자격요건",
    "preferred": "우대사항",
}

# job_description 필드명 → 내부 chunk_type 키
JD_FIELD_TO_KEY = {
    "기술스택": "skills",
    "주요업무": "main_tasks",
    "자격요건": "requirements",
    "우대사항": "preferred",
}


def _strip_bullet(line: str) -> str:
    """줄 앞의 불릿 기호(-, ■, ·, •, ㆍ), 숫자괄호(1), 2))와 공백 제거. 문장 중간의 '• ', 'ㆍ ' 도 제거."""
    line = re.sub(r"^[\-■·•ㆍ]\s*", "", line)
    line = re.sub(r"^\d+\)\s*", "", line)
    line = re.sub(r"[•ㆍ]\s+", " ", line)  # 불릿+공백(목록 기호)만 제거. 글자•글자 형태는 유지
    line = re.sub(r" +", " ", line)  # 연속 공백 하나로
    return line.strip()


def _is_numbered_upper(line: str) -> bool:
    """상위 번호(1), 2), 3)) 여부"""
    return bool(re.match(r"^\d+\)\s", line))


def _is_dash_or_block_upper(line: str) -> bool:
    """상위 불릿(-/■) 여부"""
    return bool(re.match(r"^[\-■]\s", line))


def _is_upper(line: str) -> bool:
    """상위(1)/-/■) 여부"""
    return _is_numbered_upper(line) or _is_dash_or_block_upper(line)


def _is_lower(line: str, under_numbered: bool) -> bool:
    """하위 여부. under_numbered면 - 가 하위, 아니면 ·/•/ㆍ 가 하위."""
    if under_numbered:
        return bool(re.match(r"^\-", line))
    return bool(re.match(r"^[·•ㆍ]", line))


def _parse_hierarchy(text: str) -> list[tuple[str, list[str]]]:
    """
    계층 구조 텍스트 파싱.
    - 상위: 1)/2)/... 또는 -/■
    - 하위: 1) 스타일일 때 -, 그 외엔 ·
    Returns: [(상위텍스트, [하위텍스트, ...]), ...]
    """
    groups: list[tuple[str, list[str]]] = []
    current_upper: str | None = None
    current_lowers: list[str] = []
    under_numbered = False  # 현재 상위가 1) 스타일이면 True → - 가 하위

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if _is_numbered_upper(line):
            if current_upper is not None:
                groups.append((current_upper, current_lowers))
            current_upper = _strip_bullet(line)
            current_lowers = []
            under_numbered = True

        elif under_numbered and re.match(r"^\-", line):
            # 1) 스타일 아래의 - 는 하위
            sub = _strip_bullet(line)
            if sub and current_upper is not None:
                current_lowers.append(sub)

        elif _is_dash_or_block_upper(line):
            if current_upper is not None:
                groups.append((current_upper, current_lowers))
            current_upper = _strip_bullet(line)
            current_lowers = []
            under_numbered = False

        elif _is_lower(line, under_numbered):
            sub = _strip_bullet(line)
            if sub:
                if current_upper is not None:
                    current_lowers.append(sub)
                else:
                    groups.append((sub, []))

        else:
            cleaned = _strip_bullet(line)
            if not cleaned:
                continue
            if current_upper is None:
                groups.append((cleaned, []))
            else:
                current_lowers.append(cleaned)

    if current_upper is not None:
        groups.append((current_upper, current_lowers))

    return groups


def _build_chunk_text(bracket_label: str, upper: str, lowers: list[str]) -> str:
    """[bracket_label] -상위:하위1, 하위2 형식 생성"""
    if lowers:
        return f"{bracket_label}에는 {upper}가 있다. 자세한 내용은 {', '.join(lowers)}이다."
    return f"{bracket_label}는 {upper}"


def _chunk_skills(text: str) -> list[str]:
    """
    기술스택 → 1 chunk.
    쉼표/줄바꿈/불릿 혼합을 파싱해 단일 chunk_text 반환.
    """
    if not text:
        return []

    items: list[str] = []
    for line in text.splitlines():
        cleaned = _strip_bullet(line.strip())
        for item in cleaned.split(","):
            item = item.strip()
            if item:
                items.append(item)

    if not items:
        return []

    label = CHUNK_TYPES["skills"]
    return [f"{label}은 {', '.join(items)}이다."]


def _chunk_hierarchical(text: str, key: str) -> list[str]:
    """
    계층 구조 텍스트 → chunk_text 리스트.
    main_tasks / requirements / preferred 공용.
    """
    if not text:
        return []

    label = CHUNK_TYPES[key]
    return [
        _build_chunk_text(label, upper, lowers)
        for upper, lowers in _parse_hierarchy(text)
        if upper
    ]


def chunk_job(job: dict) -> Iterator[dict]:
    """Cleaning 출력 1건 → chunk dict yield"""
    job_post_id = job.get("job_post_id", "")
    job_category = job.get("job_category", "")
    post_title = job.get("post_title", "")
    jd = job.get("job_description") or {}

    chunk_idx = 1

    def _make(key: str, chunk_text: str) -> dict:
        nonlocal chunk_idx
        record = {
            "chunk_type": CHUNK_TYPES[key],
            "chunk_id": f"{job_post_id}_{chunk_idx}",
            "chunk_text": chunk_text,
            "job_post_id": job_post_id,
            "job_category": job_category,
            "post_title": post_title,
            "job_post_url": job.get("job_post_url", ""),
        }
        chunk_idx += 1
        return record

    chunks: list[dict] = []
    # 1. 기술스택
    for text in _chunk_skills(jd.get("기술스택", "")):
        chunks.append(_make("skills", text))
    # 2. 주요업무
    for text in _chunk_hierarchical(jd.get("주요업무", ""), "main_tasks"):
        chunks.append(_make("main_tasks", text))
    # 3. 자격요건
    for text in _chunk_hierarchical(jd.get("자격요건", ""), "requirements"):
        chunks.append(_make("requirements", text))
    # 4. 우대사항
    for text in _chunk_hierarchical(jd.get("우대사항", ""), "preferred"):
        chunks.append(_make("preferred", text))

    for record in chunks:
        yield record


def run(
    input_path: str | Path,
    output_dir: str | Path | None = None,
) -> Path:
    """
    Cleaning JSON 로드 → Chunking 적용 → 저장

    Args:
        input_path: cleaning 결과 JSON 경로
        output_dir: 출력 디렉터리 (기본: data/chunking)

    Returns:
        저장된 파일 경로
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir) if output_dir else Path("data/chunking")
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(input_path, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    chunks = [chunk for job in jobs for chunk in chunk_job(job)]
    for i, rec in enumerate(chunks, start=1):
        rec["chunk_no"] = i  # 전체 청킹 데이터에서의 순번 (몇 건인지 확인용)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = output_dir / f"chunking_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        nomalizing_files = sorted(Path("data/nomalizing").glob("nomalizing_*.json"))
        if not nomalizing_files:
            print("에러: data/cleaning 디렉터리에 nomalizing_*.json 파일이 없습니다.")
            print("사용법: python src/retrieval/chunking.py <input_file>")
            sys.exit(1)
        input_file = nomalizing_files[-1]
        print(f"입력 파일: {input_file}")

    out = run(input_file)
    print(f"Chunking 완료: {out}")
