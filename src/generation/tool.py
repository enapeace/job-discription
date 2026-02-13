"""
Generation 단계에서 사용할 Tool 함수들

사용자 질의를 검색에 최적화된 형태로 정규화하는 함수들을 포함합니다.
"""

# TODO: 사용자 질의 정규화 Tool 구현
# 
# 목적: 사용자가 입력한 기술스택 질의를 검색에 최적화된 형태로 정규화
# 
# 구현 계획:
# 1. normalize_query_stack(query: str) -> list[str]
#    - 사용자 질의의 기술스택을 정규화하여 검색에 사용
#    - src/retrieval/nomalizing.py의 normalize_query_stack 함수 활용
#    - 예: "React, Python, DeepLearning" -> ["react", "python", "deep_learning"]
#    - 예: "AI/인공지능" -> ["ai"]
# 
# 2. normalize_query_experience(query: str) -> tuple[int | None, int | None]
#    - 사용자 질의의 경력 조건을 파싱
#    - src/retrieval/nomalizing.py의 parse_experience 함수 활용
#    - 예: "신입" -> (0, 0)
#    - 예: "1~3년" -> (1, 3)
# 
# 
# 4. normalize_query_location(query: str) -> tuple[str, str, str]
#    - 사용자 질의의 위치 조건을 파싱
#    - src/retrieval/nomalizing.py의 parse_location 함수 활용
#    - 예: "서울 강남구" -> ("서울", "강남구", "")
# 
# 사용 예시:
#   from src.retrieval.nomalizing import (
#       normalize_stack as normalize_query_stack,
#       parse_experience as normalize_query_experience,
#       parse_education as normalize_query_education,
#       parse_location as normalize_query_location,
#   )
#   
#   # 또는 wrapper 함수로 구현하여 generation 단계에서 사용
#   def normalize_user_query(query: dict) -> dict:
#       return {
#           "stack": normalize_query_stack(query.get("stack", "")),
#           "experience": normalize_query_experience(query.get("experience", "")),
#           "education": normalize_query_education(query.get("education", "")),
#           "location": normalize_query_location(query.get("location", "")),
#       }
