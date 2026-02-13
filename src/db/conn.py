"""
PostgreSQL 연결 공용 모듈

환경변수: DATABASE_URL 또는 POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB
"""

import os
from urllib.parse import quote_plus

import psycopg2


def get_conn():
    """환경변수로 PostgreSQL 연결을 만들고 반환한다."""
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
