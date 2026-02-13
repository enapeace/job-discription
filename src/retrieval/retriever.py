"""
RETRIEVER - 쿼리 임베딩 및 벡터 검색

질의 문자열 → 임베딩 → chunks 테이블 코사인 유사도 검색 → top_k 청크 반환
"""

import json

from openai import OpenAI

from db.conn import get_conn

EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_TOP_K = 10


def embed_query(client: OpenAI, query: str, model: str = EMBEDDING_MODEL) -> list[float]:
    """질의 문자열을 임베딩 벡터로 변환"""
    resp = client.embeddings.create(model=model, input=query)
    return resp.data[0].embedding


def vector_search(
    conn,
    embedding: list[float],
    top_k: int = DEFAULT_TOP_K,
) -> list[dict]:
    """
    코사인 유사도 벡터 검색 → top_k 청크 반환

    Returns:
        [{"chunk_id", "chunk_type", "chunk_text", "job_post_id", "job_category",
          "post_title", "job_post_url", "score"}, ...]
    """
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

    cols = [
        "chunk_id", "chunk_type", "chunk_text",
        "job_post_id", "job_category", "post_title", "job_post_url", "score",
    ]
    return [dict(zip(cols, row)) for row in rows]
