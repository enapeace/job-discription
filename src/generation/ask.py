"""
터미널에서 사용자 질의를 입력받아 RAG 답변을 출력합니다.
빈 입력 또는 'quit'/'exit'/'q' 입력 시 종료.
"""

from dotenv import load_dotenv

from llm import generate

PROMPT = "질문을 입력하세요 (종료: Enter만 입력 또는 quit): "


def main():
    load_dotenv()
    print("채용 공고 검색 도우미 (RAG)\n")

    while True:
        try:
            query = input(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not query or query.lower() in ("quit", "exit", "q"):
            print("종료합니다.")
            break

        print()
        answer, chunks, tools_used = generate(query, return_chunks=True)
        print(f"[로그] 검색된 청크 수: {len(chunks)}개")
        for i, c in enumerate(chunks, 1):
            print(f"  [{i}] chunk_id={c['chunk_id']}")
            print(f"      chunk_text={c['chunk_text'][:80]}{'...' if len(c['chunk_text']) > 80 else ''}")
        print()
        if tools_used:
            print(f"[사용한 툴] {', '.join(tools_used)}")
        else:
            print("[사용한 툴] (없음)")
        print(f"질문: {query}")
        print(f"답변:\n{answer}\n")


if __name__ == "__main__":
    main()
