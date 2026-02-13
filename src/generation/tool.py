"""
Generation 단계에서 사용할 Tool 함수들

- get_jobs_title_link: 근거 청크들의 job_post_id로 jobs 테이블 조회 → 공고 제목·링크 제공
- get_job_descriptions: 직무 관련 질문 시 검색된 청크 공고 n개의 job_description 조회 → 참고하여 답변
- get_job_detail: job_post_id로 공고 상세 조회 (company 등)
"""

from db.conn import get_conn

# OpenAI function calling 스키마: 공고 상세(회사 정보 등) 조회
TOOL_GET_JOB_DETAIL = {
    "type": "function",
    "function": {
        "name": "get_job_detail",
        "description": (
            "job_post_id로 채용 공고의 상세 정보를 가져옵니다. "
            "회사(company) 정보, 복지·채용 절차·경력·근무지 등이 필요할 때 사용하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "job_post_id": {
                    "type": "string",
                    "description": "조회할 채용 공고 ID (예: '52895679')",
                }
            },
            "required": ["job_post_id"],
        },
    },
}


def get_job_detail(conn, job_post_id: str) -> dict | None:
    """
    job_post_id로 공고 상세 조회. company 컬럼 포함.

    Args:
        conn: psycopg2 연결 (None이면 db.conn.get_conn()으로 생성 후 사용 후 닫음)
        job_post_id: 공고 ID

    Returns:
        job_post_id, job_category, post_title, job_post_url, company,
        requirements, job_description, hiring_process, experience_*, location_* 등
    """
    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    try:
        sql = """
            SELECT job_post_id, job_category, post_title, job_post_url,
                   requirements, job_description, hiring_process, company,
                   experience_raw, experience_min_years, experience_max_years,
                   location_raw, location_city, location_district, location_detail
            FROM jobs
            WHERE job_post_id = %s
        """
        with conn.cursor() as cur:
            cur.execute(sql, (job_post_id,))
            row = cur.fetchone()

        if row is None:
            return None

        cols = [
            "job_post_id", "job_category", "post_title", "job_post_url",
            "requirements", "job_description", "hiring_process", "company",
            "experience_raw", "experience_min_years", "experience_max_years",
            "location_raw", "location_city", "location_district", "location_detail",
        ]
        return dict(zip(cols, row))
    finally:
        if own_conn:
            conn.close()


# OpenAI function calling 스키마: 공고 제목·링크 조회
TOOL_GET_JOBS_TITLE_LINK = {
    "type": "function",
    "function": {
        "name": "get_jobs_title_link",
        "description": (
            "검색된 청크에 나온 공고 ID들로 채용 공고의 제목과 링크 목록을 가져옵니다. "
            "사용자에게 추천 공고 목록을 제목과 링크로 정리해서 보여줄 때 사용하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "job_post_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "조회할 채용 공고 ID 목록 (예: ['52895679', '52895680'])",
                }
            },
            "required": ["job_post_ids"],
        },
    },
}


def get_jobs_title_link(conn, job_post_ids: list[str]) -> list[dict]:
    """
    job_post_id 목록으로 jobs 테이블에서 공고 제목·링크만 조회.

    Args:
        conn: psycopg2 연결 (None이면 db.conn.get_conn()으로 생성 후 사용 후 닫음)
        job_post_ids: 공고 ID 목록

    Returns:
        [{"job_post_id": str, "post_title": str, "job_post_url": str}, ...]
    """
    if not job_post_ids:
        return []

    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    try:
        sql = """
            SELECT job_post_id, post_title, job_post_url
            FROM jobs
            WHERE job_post_id = ANY(%s)
        """
        with conn.cursor() as cur:
            cur.execute(sql, (job_post_ids,))
            rows = cur.fetchall()

        return [
            {"job_post_id": r[0], "post_title": r[1], "job_post_url": r[2] or ""}
            for r in rows
        ]
    finally:
        if own_conn:
            conn.close()


# OpenAI function calling 스키마: 직무 관련 질문용 job_description 조회
TOOL_GET_JOB_DESCRIPTIONS = {
    "type": "function",
    "function": {
        "name": "get_job_descriptions",
        "description": (
            "직무·업무·역할·담당업무 관련 질문에 답할 때 사용합니다. "
            "검색된 청크에 나온 공고 ID들 중 상위 n개의 공고에 대한 전체 job_description(직무소개)을 가져옵니다. "
            "가져온 직무소개를 참고해 사용자 질문에 맞게 답하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "job_post_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "검색된 청크에서 추린 공고 ID 목록 (질문에 가장 적합한 순)",
                },
                "n": {
                    "type": "integer",
                    "description": "가져올 공고 개수 (기본 5, 최대 10)",
                    "default": 5,
                },
            },
            "required": ["job_post_ids"],
        },
    },
}


def get_job_descriptions(conn, job_post_ids: list[str], n: int = 5) -> list[dict]:
    """
    질문에 적합한 청크 공고 n개의 job_description 컬럼 조회.
    직무 관련 질문 시 참고용으로 사용.

    Args:
        conn: psycopg2 연결 (None이면 db.conn.get_conn()으로 생성 후 사용 후 닫음)
        job_post_ids: 공고 ID 목록 (검색된 청크에서 추린 순서 유지)
        n: 가져올 개수 (기본 5, 최대 10)

    Returns:
        [{"job_post_id": str, "post_title": str, "job_description": dict}, ...]
    """
    if not job_post_ids:
        return []
    ids = job_post_ids[: min(n, 10)]

    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    try:
        sql = """
            SELECT job_post_id, post_title, job_description
            FROM jobs
            WHERE job_post_id = ANY(%s)
        """
        with conn.cursor() as cur:
            cur.execute(sql, (ids,))
            rows = cur.fetchall()

        # 요청한 id 순서 유지
        by_id = {r[0]: {"job_post_id": r[0], "post_title": r[1], "job_description": r[2] or {}} for r in rows}
        return [by_id[jid] for jid in ids if jid in by_id]
    finally:
        if own_conn:
            conn.close()
