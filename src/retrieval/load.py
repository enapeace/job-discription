"""
LOAD - PostgreSQL + pgvector 적재

PIPELINE_PLAN.md 6. LOAD 스펙 구현
- chunks 테이블: embedding_*.json → chunk_id, chunk_text, embedding(vector), 메타데이터
- jobs 테이블  : nomalizing_*.json → job_post_id, normalized 필드, company, job_description 등

환경변수: DATABASE_URL 또는 POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB
"""

import json
import os
from pathlib import Path
from urllib.parse import quote_plus

import psycopg2
from psycopg2.extras import execute_values

# DDL: pgvector 확장 + 두 테이블 생성
DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS jobs (
    job_post_id          TEXT PRIMARY KEY,
    job_category         TEXT,
    post_title           TEXT,
    job_post_url         TEXT,
    requirements         JSONB,
    job_description      JSONB,
    hiring_process       TEXT,
    company              JSONB,
    experience_raw       TEXT,
    experience_min_years INT,
    experience_max_years INT,
    location_raw         TEXT,
    location_city        TEXT,
    location_district    TEXT,
    location_detail      TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id     TEXT PRIMARY KEY,
    chunk_type   TEXT,
    chunk_text   TEXT,
    embedding    vector(1536),
    job_post_id  TEXT REFERENCES jobs(job_post_id),
    job_category TEXT,
    post_title   TEXT,
    job_post_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING hnsw (embedding vector_cosine_ops);
"""


def get_conn():
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


def create_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    print("  테이블 생성/확인 완료")


def load_jobs(conn, nomalizing_path: Path) -> int:
    """nomalizing_*.json → jobs 테이블 upsert"""
    with open(nomalizing_path, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    rows = []
    for job in jobs:
        norm = job.get("normalized") or {}
        rows.append((
            job.get("job_post_id"),
            job.get("job_category"),
            job.get("post_title"),
            job.get("job_post_url"),
            json.dumps(job.get("requirements"), ensure_ascii=False),
            json.dumps(job.get("job_description"), ensure_ascii=False),
            job.get("hiring_process"),
            json.dumps(job.get("company"), ensure_ascii=False),
            norm.get("experience_raw"),
            norm.get("experience_min_years"),
            norm.get("experience_max_years"),
            norm.get("location_raw"),
            norm.get("location_city"),
            norm.get("location_district"),
            norm.get("location_detail"),
        ))

    sql = """
        INSERT INTO jobs (
            job_post_id, job_category, post_title, job_post_url,
            requirements, job_description, hiring_process, company,
            experience_raw, experience_min_years, experience_max_years,
            location_raw, location_city, location_district, location_detail
        ) VALUES %s
        ON CONFLICT (job_post_id) DO UPDATE SET
            job_category         = EXCLUDED.job_category,
            post_title           = EXCLUDED.post_title,
            job_post_url         = EXCLUDED.job_post_url,
            requirements         = EXCLUDED.requirements,
            job_description      = EXCLUDED.job_description,
            hiring_process       = EXCLUDED.hiring_process,
            company              = EXCLUDED.company,
            experience_raw       = EXCLUDED.experience_raw,
            experience_min_years = EXCLUDED.experience_min_years,
            experience_max_years = EXCLUDED.experience_max_years,
            location_raw         = EXCLUDED.location_raw,
            location_city        = EXCLUDED.location_city,
            location_district    = EXCLUDED.location_district,
            location_detail      = EXCLUDED.location_detail
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    print(f"  jobs 테이블 적재 완료: {len(rows)}건")
    return len(rows)


def _chunk_record_to_row(c: dict) -> tuple | None:
    emb = c.get("embedding")
    if emb is None:
        return None
    return (
        c.get("chunk_id"),
        c.get("chunk_type"),
        c.get("chunk_text"),
        json.dumps(emb),
        c.get("job_post_id"),
        c.get("job_category"),
        c.get("post_title"),
        c.get("job_post_url"),
    )


def load_chunks(conn, embedding_path: Path) -> int:
    """embedding_*.jsonl 또는 embedding_*.json(배열) → chunks 테이블 upsert"""
    rows = []
    with open(embedding_path, "r", encoding="utf-8") as f:
        peek = f.read(50).lstrip()
    is_array = peek.startswith("[")
    with open(embedding_path, "r", encoding="utf-8") as f:
        if is_array:
            data = json.load(f)
            for c in data:
                row = _chunk_record_to_row(c)
                if row is not None:
                    rows.append(row)
        else:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                c = json.loads(line)
                row = _chunk_record_to_row(c)
                if row is not None:
                    rows.append(row)

    sql = """
        INSERT INTO chunks (
            chunk_id, chunk_type, chunk_text, embedding,
            job_post_id, job_category, post_title, job_post_url
        ) VALUES %s
        ON CONFLICT (chunk_id) DO UPDATE SET
            chunk_type   = EXCLUDED.chunk_type,
            chunk_text   = EXCLUDED.chunk_text,
            embedding    = EXCLUDED.embedding,
            job_category = EXCLUDED.job_category,
            post_title   = EXCLUDED.post_title,
            job_post_url = EXCLUDED.job_post_url
    """
    with conn.cursor() as cur:
        execute_values(
            cur, sql, rows,
            template="(%s, %s, %s, %s::vector, %s, %s, %s, %s)",
        )
    conn.commit()
    print(f"  chunks 테이블 적재 완료: {len(rows)}건")
    return len(rows)


def run(
    embedding_path: str | Path,
    nomalizing_path: str | Path,
) -> None:
    """
    embedding_*.json + nomalizing_*.json → PostgreSQL 적재

    Args:
        embedding_path: 임베딩 결과 JSON 경로
        nomalizing_path: nomalizing 결과 JSON 경로
    """
    embedding_path = Path(embedding_path)
    nomalizing_path = Path(nomalizing_path)

    conn = get_conn()
    try:
        create_tables(conn)
        load_jobs(conn, nomalizing_path)
        load_chunks(conn, embedding_path)
    finally:
        conn.close()
    print("Load 완료")


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv()

    # .jsonl(권장) 또는 .json (줄 단위 JSONL 형식이면 둘 다 지원)
    embedding_files = sorted(
        list(Path("data/embedding").glob("embedding_*.jsonl"))
        + list(Path("data/embedding").glob("embedding_*.json"))
    )
    nomalizing_files = sorted(Path("data/nomalizing").glob("nomalizing_*.json"))

    if not embedding_files:
        print("에러: data/embedding 디렉터리에 embedding_*.jsonl 또는 embedding_*.json 파일이 없습니다.")
        sys.exit(1)
    if not nomalizing_files:
        print("에러: data/nomalizing 디렉터리에 nomalizing_*.json 파일이 없습니다.")
        sys.exit(1)

    embedding_file = embedding_files[-1]
    nomalizing_file = nomalizing_files[-1]
    print(f"임베딩 파일: {embedding_file}")
    print(f"정규화 파일: {nomalizing_file}")

    run(embedding_file, nomalizing_file)
