"""
AUGMENTED GENERATION - RAG

PIPELINE_PLAN.md 7. AUGMENTED GENERATION 스펙 구현
- 사용자 질의 → retriever로 벡터 검색(top_k) → gpt-4o-mini → 응답
- Tool: get_job_detail, get_jobs_title_link, get_job_descriptions
"""

import json
import sys
from pathlib import Path

from openai import OpenAI

# uv run src/generation/ask.py 실행 시 src가 패키지로 안 잡히므로 path 추가
_src_dir = Path(__file__).resolve().parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
from db.conn import get_conn
from retrieval.retriever import (
    DEFAULT_TOP_K,
    embed_query,
    vector_search,
)
from tool import (
    get_job_detail,
    get_job_descriptions,
    get_jobs_title_link,
    TOOL_GET_JOB_DETAIL,
    TOOL_GET_JOB_DESCRIPTIONS,
    TOOL_GET_JOBS_TITLE_LINK,
)

LLM_MODEL = "gpt-4o-mini"
TOP_K = DEFAULT_TOP_K


_TOOLS = [
    TOOL_GET_JOB_DETAIL,
    TOOL_GET_JOBS_TITLE_LINK,
    TOOL_GET_JOB_DESCRIPTIONS,
]

_SYSTEM_PROMPT = (
    "당신은 채용 공고 검색 도우미입니다.\n"
    "제공된 청크 데이터를 바탕으로 사용자 질문에 답하세요.\n"
    "직무·업무·역할·담당업무 관련 질문이면 get_job_descriptions 툴로 해당 공고들의 직무소개(job_description)를 가져와 참고하며 답하세요.\n"
    "추천 공고를 제목·링크로 정리해 보여줄 때는 get_jobs_title_link 툴을 사용하세요.\n"
    "특정 공고의 복지·회사 정보·채용 절차 등 상세 내용이 필요하면 get_job_detail 툴을 사용하세요.\n"
    "필요하면 여러개의 tool을 사용할 수 있습니다."
    "답변은 한국어로 합니다."
)


def _log_llm_context(messages: list, call_index: int = 0):
    """LLM에 들어가는 전체 컨텍스트(메시지 목록)를 로그로 출력"""
    def _get(m, key, default=None):
        if isinstance(m, dict):
            return m.get(key, default)
        return getattr(m, key, default)

    sep = "=" * 60
    print(f"\n[LLM 컨텍스트 로그] (API 호출 #{call_index + 1})\n{sep}")
    for m in messages:
        role = _get(m, "role", "?")
        content = _get(m, "content") or "(없음)"
        if role == "system":
            print(f"\n--- role: system ---\n{content}\n")
        elif role == "user":
            print(f"\n--- role: user ---\n{content}\n")
        elif role == "assistant":
            part = content or ""
            tool_calls = _get(m, "tool_calls") or []
            if tool_calls:
                tcs = []
                for tc in tool_calls:
                    fn = _get(tc, "function") or _get(tc, "function")
                    if isinstance(fn, dict):
                        tcs.append({"name": fn.get("name"), "arguments": fn.get("arguments", "")})
                    else:
                        tcs.append({"name": _get(fn, "name"), "arguments": _get(fn, "arguments", "")})
                part += "\n[tool_calls] " + json.dumps(tcs, ensure_ascii=False)
            print(f"\n--- role: assistant ---\n{part}\n")
        elif role == "tool":
            tid = _get(m, "tool_call_id") or ""
            print(f"\n--- role: tool (id={str(tid)[:8]}...) ---\n{str(content)[:500]}{'...' if len(str(content)) > 500 else ''}\n")
    print(sep + "\n")


def generate(query: str, conn=None, return_chunks: bool = False):
    """
    사용자 질의 → RAG 응답 생성

    Args:
        query: 사용자 질의 문자열
        conn: 기존 psycopg2 연결 (없으면 환경변수 DATABASE_URL로 생성)
        return_chunks: True면 (응답문자열, 청크리스트, 사용한 툴 이름 리스트) 반환

    Returns:
        return_chunks=False: LLM 응답 문자열
        return_chunks=True: (LLM 응답 문자열, 검색된 청크 리스트, 사용한 툴 이름 리스트)
    """
    client = OpenAI()
    _conn = conn or get_conn()
    close_conn = conn is None
    tools_used = []

    try:
        # 1. 쿼리 임베딩 (retriever)
        query_emb = embed_query(client, query)

        # 2. 벡터 검색 top_k (retriever)
        chunks = vector_search(_conn, query_emb, top_k=TOP_K)

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

        api_call_index = 0
        while True:
            _log_llm_context(messages, api_call_index)
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            messages.append(msg)
            api_call_index += 1

            if not msg.tool_calls:
                if return_chunks:
                    return msg.content, chunks, tools_used
                return msg.content

            tool_names = [tc.function.name for tc in msg.tool_calls]
            tools_used.extend(tool_names)
            print(f"[툴 호출] {', '.join(tool_names)}")

            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                if tool_call.function.name == "get_job_detail":
                    detail = get_job_detail(_conn, args["job_post_id"])
                    result = (
                        json.dumps(detail, ensure_ascii=False, default=str)
                        if detail
                        else "해당 공고를 찾을 수 없습니다."
                    )
                elif tool_call.function.name == "get_jobs_title_link":
                    items = get_jobs_title_link(_conn, args.get("job_post_ids", []))
                    result = json.dumps(items, ensure_ascii=False, default=str)
                elif tool_call.function.name == "get_job_descriptions":
                    n = args.get("n", 5)
                    items = get_job_descriptions(
                        _conn, args.get("job_post_ids", []), n=min(max(1, n), 10)
                    )
                    result = json.dumps(items, ensure_ascii=False, default=str)
                else:
                    result = "알 수 없는 툴입니다."
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

    finally:
        if close_conn:
            _conn.close()

