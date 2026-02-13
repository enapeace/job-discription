"""
AUGMENTED GENERATION - RAG

PIPELINE_PLAN.md 7. AUGMENTED GENERATION 스펙 구현
- 사용자 질의 → retriever로 벡터 검색(top_k) → gpt-4o-mini → 응답
- Tool: get_company_info, get_jobs_title_link, get_job_descriptions
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
    get_company_info,
    get_job_descriptions,
    get_jobs_title_link,
    TOOL_GET_COMPANY_INFO,
    TOOL_GET_JOB_DESCRIPTIONS,
    TOOL_GET_JOBS_TITLE_LINK,
)

LLM_MODEL = "gpt-4o-mini"
TOP_K = DEFAULT_TOP_K


_TOOLS = [
    TOOL_GET_COMPANY_INFO,
    TOOL_GET_JOBS_TITLE_LINK,
    TOOL_GET_JOB_DESCRIPTIONS,
]

_SYSTEM_PROMPT = (
    "당신은 채용 공고 검색 도우미입니다.\n"
    "제공된 청크 데이터를 바탕으로 사용자 질문에 답하세요.\n"
    "직무·업무·역할·담당업무 관련 질문이면 get_job_descriptions 툴로 해당 공고들의 직무소개(job_description)를 가져와 참고하며 답하세요.\n"
    "추천 공고를 제목·링크로 정리해 보여줄 때는 get_jobs_title_link 툴을 사용하세요.\n"
    "특정 공고의 회사 정보(복지, 직원 수, 연봉, 매출액 등)가 필요하면 get_company_info 툴을 사용하세요.\n"
    "필요하면 여러개의 tool을 사용할 수 있습니다."
    "답변은 한국어로 합니다."
)


def _rewrite_query_for_search(client: OpenAI, original_query: str) -> str:
    """
    사용자 질의를 채용 공고 검색에 적합한 핵심 키워드/질문으로 재작성.
    인사말, 개인 정보 등 노이즈를 제거하고 채용 공고 내용과 관련된 핵심만 추출.
    """
    REWRITE_MODEL = "gpt-4o-mini"
    REWRITE_PROMPT = (
        "사용자의 질문에서 JD(직무, 기술스택, 업무, 자격요건)와 관련된 핵심 키워드와 질문만 추출하여 간결하게 재작성하세요. 기술스택이 한국어로 적힌 경우, 기술스택 단어만 영어로 변환하세요.\n\n"
        "제거할 내용:\n"
        "- 인사말 (안녕하세요, 감사합니다 등)\n"
        "- 개인 정보 (저는, 제가 등)\n"
        "- 불필요한 수식어\n\n"
        "유지할 내용:\n"
        "- 기술스택, 직무, 업무 내용, 자격요건, 회사 정보 등 채용 공고와 관련된 핵심 키워드\n"
        "- 질문의 의도 (예: 'Python 개발자 채용 공고', '코딩테스트 없는 회사')\n\n"
        "원본 질문: {query}\n\n"
        "재작성된 질문 (핵심만, 간결하게):"
    )
    
    try:
        response = client.chat.completions.create(
            model=REWRITE_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": REWRITE_PROMPT.format(query=original_query),
                }
            ],
            temperature=0,
            max_tokens=100,  # 간결하게 재작성
        )
        rewritten = response.choices[0].message.content.strip()
        
        # 재작성 결과가 너무 짧거나 비어있으면 원본 사용
        if len(rewritten) < 3:
            print(f"[질의 재작성] 재작성 결과가 너무 짧아 원본 사용: {original_query}")
            return original_query
        
        print(f"[질의 재작성]")
        print(f"  원본: {original_query}")
        print(f"  재작성: {rewritten}")
        return rewritten
    except Exception as e:
        print(f"[질의 재작성 실패] 원본 사용: {e}")
        return original_query


def _evaluate_chunks(client: OpenAI, query: str, chunks: list[dict]) -> list[dict]:
    """
    벡터 검색으로 가져온 청크들 중 질문에 적합한 청크만 필터링.
    각 청크의 내용이 질문과 관련이 있는지 LLM으로 평가.
    관련 없다고 판별된 청크(NO)는 제외하고, 관련 있다고 판별된 청크(YES)만 반환합니다.
    """
    if not chunks:
        return []

    EVAL_MODEL = "gpt-4o-mini"  # 평가용 모델 (빠르고 저렴)
    EVAL_PROMPT = (
        "다음 청크 내용이 사용자 질문과 관련이 있는지 판단하세요.\n\n"
        "관련이 있으면 'YES', 관련이 없으면 'NO'만 답변하세요.\n\n"
        "사용자 질문: {query}\n\n"
        "청크 내용:\n{chunk_text}\n\n"
        "답변 (YES/NO만):"
    )

    relevant_chunks = []
    total_count = len(chunks)
    print(f"[청크 평가 시작] 총 {total_count}개 청크 평가 중...")

    for i, chunk in enumerate(chunks, 1):
        chunk_text = chunk.get("chunk_text", "")
        if not chunk_text:
            continue  # 텍스트 없는 청크는 건너뜀

        # 각 청크에 대해 간단한 평가 요청
        eval_messages = [
            {
                "role": "user",
                "content": EVAL_PROMPT.format(query=query, chunk_text=chunk_text[:500]),  # 토큰 절약을 위해 앞부분만
            }
        ]

        try:
            response = client.chat.completions.create(
                model=EVAL_MODEL,
                messages=eval_messages,
                temperature=0,  # 일관성 위해 0
                max_tokens=10,  # YES/NO만 필요
            )
            answer = response.choices[0].message.content.strip().upper()

            if "YES" in answer:
                # 관련 있다고 판별된 청크만 추가
                relevant_chunks.append(chunk)
                print(f"  [{i}/{total_count}] ✓ 관련 있음 ({len(relevant_chunks)}개): {chunk.get('chunk_id', '?')[:20]}...")
            else:
                # 관련 없다고 판별된 청크는 제외 (버림)
                print(f"  [{i}/{total_count}] ✗ 관련 없음 (제외): {chunk.get('chunk_id', '?')[:20]}...")
        except Exception as e:
            # 평가 실패 시 안전하게 제외 (에러 발생한 청크는 포함하지 않음)
            print(f"  [{i}/{total_count}] ⚠ 평가 실패 (제외): {e}")

    relevant_count = len(relevant_chunks)
    excluded_count = total_count - relevant_count
    print(f"\n[청크 평가 완료]")
    print(f"  ✓ 관련 있음: {relevant_count}개")
    print(f"  ✗ 관련 없음 (제외): {excluded_count}개")
    print(f"  총 평가: {total_count}개 → {relevant_count}개 사용 ({excluded_count}개 제외)")
    return relevant_chunks  # 관련 있는 청크만 반환


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
    """
    client = OpenAI()
    _conn = conn or get_conn()
    close_conn = conn is None
    tools_used = []
    original_query = query  # 원본 질의는 최종 답변 생성 시 사용

    try:
        # 0. 질의 재작성 (임베딩된 데이터로 검색하기 적합한 핵심 키워드/질문으로 재작성)
        search_query = _rewrite_query_for_search(client, original_query)
        print(f"[질의 재작성] {search_query}")
        
        # 1. 재작성된 쿼리로 임베딩 (retriever)
        query_emb = embed_query(client, search_query)

        # 2. 벡터 검색 top_k (retriever) - 재작성된 쿼리 사용
        chunks = vector_search(_conn, query_emb, top_k=TOP_K)
        for c in chunks:
            print(f"  [공고ID: {c['job_post_id']}] {c['post_title']}\n")
            print(f"  {c['chunk_text']}\n")
            print(f"  유사도: {c['score']:.3f}\n")

        # 2.5. 청크 평가 및 필터링 (질문에 적합한 청크만 선택) - 원본 쿼리로 평가
        original_chunks = chunks.copy()  # 원본 청크 백업 (fallback용)
        relevant_chunks = _evaluate_chunks(client, original_query, chunks)
        
        # 모든 청크가 필터링된 경우 fallback: 원본 청크 중 유사도 상위 3개 사용
        if not relevant_chunks and original_chunks:
            print("[경고] 모든 청크가 관련 없다고 판별되었습니다.")
            print("[Fallback] 유사도 상위 3개 청크를 사용합니다.")
            chunks = original_chunks[:3]  # 유사도가 높은 상위 3개 사용
        else:
            chunks = relevant_chunks  # 필터링된 청크 사용
        
        if not chunks:
            print("[경고] 사용 가능한 청크가 없습니다. 빈 컨텍스트로 답변을 생성합니다.")
        
        print(f"[최종 사용 청크] {len(chunks)}개 청크가 답변 생성에 사용됩니다.\n")

        # 3. 컨텍스트 구성
        context_parts = []
        for c in chunks:
            context_parts.append(
                f"[공고ID: {c['job_post_id']}] {c['post_title']}\n"
                f"{c['chunk_text']}\n"
            )
        context = "\n\n---\n\n".join(context_parts)

        # 4. LLM 호출 (tool calling loop)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"다음 채용 공고 데이터를 참고하여 질문에 답해주세요. 질문의 궁극적 목적에 맞게 답변해주세요.\n\n"
                    f"{context}\n\n질문: {original_query}"
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
                if tool_call.function.name == "get_company_info":
                    company_info = get_company_info(_conn, args["job_post_id"])
                    if company_info:
                        # 회사 정보를 읽기 쉬운 형식으로 변환
                        company = company_info.get("company", {})
                        result_parts = [
                            f"공고 제목: {company_info.get('post_title', '')}",
                            f"회사명: {company.get('company_name', '정보 없음')}",
                            f"회사 소개 링크: {company.get('company_url', '정보 없음')}",
                            f"직원 수: {company.get('전체 직원수', '정보 없음')}",
                            f"평균 연봉: {company.get('평균 연봉', '정보 없음')}",
                            f"매출액: {company.get('매출액', '정보 없음')}",
                            f"영업이익: {company.get('영업이익', '정보 없음')}",
                        ]
                        if company.get("복지 및 혜택"):
                            welfare = company["복지 및 혜택"]
                            # 너무 길면 앞부분만 (500자 제한)
                            if len(welfare) > 500:
                                welfare = welfare[:500] + "..."
                            result_parts.append(f"복지 및 혜택:\n{welfare}")
                        if company.get("company_tags"):
                            tags = ", ".join(company["company_tags"])
                            result_parts.append(f"회사 태그: {tags}")
                        result = "\n".join(result_parts)
                    else:
                        result = "해당 공고를 찾을 수 없습니다."
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

