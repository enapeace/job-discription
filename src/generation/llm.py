"""
AUGMENTED GENERATION - RAG

PIPELINE_PLAN.md 7. AUGMENTED GENERATION 스펙 구현
- 사용자 질의 → 벡터 검색(top-10) → gpt-4o-mini → 응답
- Tool: get_job_detail (job_post_id 기준 jobs + chunks join)
"""

import json
import os
from urllib.parse import quote_plus

import psycopg2
from openai import OpenAI

LLM_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
TOP_K = 10


def _get_conn():
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    user = os.environ.get("POSTGRES_USER", "root")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "dj-project")
    url = f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"
    return psycopg2.connect(url)


def _embed_query(client: OpenAI, query: str) -> list[float]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=query)
    return resp.data[0].embedding


def _vector_search(conn, embedding: list[float], top_k: int = TOP_K) -> list[dict]:
    """코사인 유사도 벡터 검색 → top_k 청크 반환"""
    sql = """
        SELECT chunk_id, chunk_type, chunk_text,
               job_post_id, job_category, post_title, job_post_url,
               1 - (embedding <=> %s::vector) AS score
        FROM chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    emb_str = json.dumps(embedding)
    with conn.cursor() as cur:
        cur.execute(sql, (emb_str, emb_str, top_k))
        rows = cur.fetchall()

    cols = ["chunk_id", "chunk_type", "chunk_text",
            "job_post_id", "job_category", "post_title", "job_post_url", "score"]
    return [dict(zip(cols, row)) for row in rows]


def _get_job_detail(conn, job_post_id: str) -> dict | None:
    """job_post_id로 공고 전체 정보 조회"""
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


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_job_detail",
            "description": (
                "job_post_id로 채용 공고의 상세 정보를 가져옵니다. "
                "검색 결과만으로 답변하기 어렵거나, 특정 공고의 복지·회사 정보·채용 절차 등 "
                "상세 내용이 필요할 때 사용하세요."
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
]

_SYSTEM_PROMPT = (
    "당신은 채용 공고 검색 도우미입니다.\n"
    "제공된 청크 데이터를 바탕으로 사용자 질문에 답하세요.\n"
    "특정 공고의 복지·회사 정보·채용 절차 등 상세 내용이 필요하면 get_job_detail 툴을 사용하세요.\n"
    "답변은 한국어로 합니다."
)


def generate(query: str, conn=None, return_chunks: bool = False):
    """
    사용자 질의 → RAG 응답 생성

    Args:
        query: 사용자 질의 문자열
        conn: 기존 psycopg2 연결 (없으면 환경변수 DATABASE_URL로 생성)
        return_chunks: True면 (응답문자열, 청크리스트) 반환

    Returns:
        return_chunks=False: LLM 응답 문자열
        return_chunks=True: (LLM 응답 문자열, 검색된 청크 리스트)
    """
    client = OpenAI()
    _conn = conn or _get_conn()
    close_conn = conn is None

    try:
        # 1. 쿼리 임베딩
        query_emb = _embed_query(client, query)

        # 2. 벡터 검색 top-10
        chunks = _vector_search(_conn, query_emb)

        # 3. 컨텍스트 구성
        context_parts = []
        for c in chunks:
            context_parts.append(
                f"[공고ID: {c['job_post_id']}] {c['post_title']} ({c['job_category']})\n"
                f"{c['chunk_type']}: {c['chunk_text']}\n"
                f"유사도: {c['score']:.3f}"
            )
        context = "\n\n---\n\n".join(context_parts)

        # 4. LLM 호출 (tool calling loop)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"다음 채용 공고 데이터를 참고하여 질문에 답해주세요.\n\n"
                    f"{context}\n\n질문: {query}"
                ),
            },
        ]

        while True:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                if return_chunks:
                    return msg.content, chunks
                return msg.content

            for tool_call in msg.tool_calls:
                if tool_call.function.name == "get_job_detail":
                    args = json.loads(tool_call.function.arguments)
                    detail = _get_job_detail(_conn, args["job_post_id"])
                    result = (
                        json.dumps(detail, ensure_ascii=False, default=str)
                        if detail
                        else "해당 공고를 찾을 수 없습니다."
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })

    finally:
        if close_conn:
            _conn.close()


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv()

    query = sys.argv[1] if len(sys.argv) > 1 else "Python을 사용하는 AI 관련 신입 채용 공고 알려줘"
    print(f"질의: {query}\n")
    answer = generate(query)
    print(f"답변:\n{answer}")
