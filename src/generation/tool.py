"""
Generation 단계에서 사용할 Tool 함수들

- get_jobs_title_link: 근거 청크들의 job_post_id로 jobs 테이블 조회 → post_title, job_post_url 조회
- get_job_descriptions: 직무 관련 질문 시 검색된 청크 공고 n개의 post_title, job_post_url, job_description 조회 → 참고하여 답변
- get_company_info: job_post_id로 공고 상세 조회 (company 정보 조회)
"""

from db.conn import get_conn

# OpenAI function calling 스키마: 회사 정보 조회
TOOL_GET_COMPANY_INFO = {
    "type": "function",
    "function": {
        "name": "get_company_info",
        "description": (
            "job_post_id로 채용 공고의 회사(company) 정보를 조회합니다. "
            "회사 정보에는 직원 수, 평균연봉, 매출액, 영업이익, 복지 및 혜택이 포함됩니다. "
            "회사 정보가 필요할 때 사용하세요."
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


def get_company_info(conn, job_post_id: str) -> dict | None:
    """
    job_post_id로 공고의 회사(company) 정보 조회.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    try:
        sql = """
            SELECT job_post_id, post_title, company
            FROM jobs
            WHERE job_post_id = %s
        """
        with conn.cursor() as cur:
            cur.execute(sql, (job_post_id,))
            row = cur.fetchone()

        if row is None:
            return None

        return {
            "job_post_id": row[0],
            "post_title": row[1],
            "company": row[2] or {}
        }
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
    """
    if not job_post_ids:
        return []
    ids = job_post_ids[: min(n, 10)]

    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    try:
        sql = """
            SELECT job_post_id, post_title, job_post_url, job_description
            FROM jobs
            WHERE job_post_id = ANY(%s)
        """
        with conn.cursor() as cur:
            cur.execute(sql, (ids,))
            rows = cur.fetchall()

        # 요청한 id 순서 유지
        by_id = {
            r[0]: {
                "job_post_id": r[0],
                "post_title": r[1],
                "job_post_url": r[2] or "",
                "job_description": r[3] or {}
            }
            for r in rows
        }
        return [by_id[jid] for jid in ids if jid in by_id]
    finally:
        if own_conn:
            conn.close()
