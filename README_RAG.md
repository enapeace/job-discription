# RAG 파이프라인 — Job Description 인사이트

## RAG란?

**Retrieval-Augmented Generation**의 약자.

| 단어 | 의미 |
|------|------|
| **Retrieval** | (외부에서) 정보를 검색·조회 |
| **Augmented** | 보강된, 강화된 |
| **Generation** | 생성 |

> 외부 지식(문서, DB, 벡터스토어 등)을 검색해서 그 정보를 기반으로 답변을 생성하는 방식

---

## 대목차

| 파트 | 파일 | 설명 |
|------|------|------|
| **R** | [README_R_Retrieval.md](./README_R_Retrieval.md) | 데이터 수집 → 정규화 → 청킹 → 임베딩 → 벡터스토어 저장 |
| **A** | [README_A_Augmented.md](./README_A_Augmented.md) | 벡터 검색 + 메타데이터 필터링 결합 |
| **G** | [README_G_Generation.md](./README_G_Generation.md) | LLM 기반 답변 생성 (gpt-4o-mini) |

---

## 전체 플로우

```
[R: Retrieval]     [A: Augmented]     [G: Generation]
데이터 준비·저장  →  검색·필터 결합  →  답변 생성
```
