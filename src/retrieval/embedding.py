"""
EMBEDDING - OpenAI text-embedding-3-small

PIPELINE_PLAN.md 5. EMBEDDING 스펙 구현
- chunking JSON → chunk_text 임베딩 생성
- 배치 응답 올 때마다 실시간으로 JSONL에 기록 (중간 실패해도 그때까지 결과 보존)
- 출력: data/embedding/embedding_*.jsonl  (1줄 = 레코드 1개)
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI

MODEL = "text-embedding-3-small"
BATCH_SIZE = 100


async def _embed_batch(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    resp = await client.embeddings.create(model=MODEL, input=texts)
    return [item.embedding for item in resp.data]


async def _embed_and_write(chunks: list[dict], output_path: Path) -> int:
    """배치 임베딩 → 결과 올 때마다 즉시 JSONL 한 줄씩 기록"""
    client = AsyncOpenAI()
    total = len(chunks)
    written = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for i in range(0, total, BATCH_SIZE):
            batch_chunks = chunks[i : i + BATCH_SIZE]
            batch_texts = [c["chunk_text"] for c in batch_chunks]

            embeddings = await _embed_batch(client, batch_texts)

            for chunk, emb in zip(batch_chunks, embeddings):
                chunk["embedding"] = emb
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            f.flush()

            written += len(batch_chunks)
            print(f"  임베딩 진행: {written}/{total}")

    return written


def run(
    input_path: str | Path,
    output_dir: str | Path | None = None,
) -> Path:
    """
    chunking JSON 로드 → 임베딩 생성 → JSONL 실시간 저장

    Args:
        input_path: chunking 결과 JSON 경로
        output_dir: 출력 디렉터리 (기본: data/embedding)

    Returns:
        저장된 파일 경로 (.jsonl)
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir) if output_dir else Path("data/embedding")
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(input_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = output_dir / f"embedding_{timestamp}.jsonl"

    print(f"총 {len(chunks)}개 청크 임베딩 시작 (모델: {MODEL})...")
    count = asyncio.run(_embed_and_write(chunks, output_path))
    print(f"임베딩 완료: {output_path} ({count}건)")
    return output_path


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv()

    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        chunking_files = sorted(Path("data/chunking").glob("chunking_*.json"))
        if not chunking_files:
            print("에러: data/chunking 디렉터리에 chunking_*.json 파일이 없습니다.")
            sys.exit(1)
        input_file = chunking_files[-1]
        print(f"입력 파일: {input_file}")

    out = run(input_file)
    print(f"출력: {out}")
