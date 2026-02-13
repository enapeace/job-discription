"""
법정동코드 전체자료.txt에서 시도/시군구만 추출하여 JSON으로 저장.
Normalizing 단계에서 location_city, location_district 파싱 정확도 향상을 위해 사용.
"""
from pathlib import Path
import json

# 법정동명 시도 표기 → location_city (약칭)
SIDO_MAP = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "부산직할시": "부산",
    "대구광역시": "대구",
    "대구직할시": "대구",
    "인천광역시": "인천",
    "인천직할시": "인천",
    "광주광역시": "광주",
    "광주직할시": "광주",
    "대전광역시": "대전",
    "대전직할시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "경기도": "경기",
    "강원도": "강원",
    "강원특별자치도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전라북도": "전북",
    "전북특별자치도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주도": "제주",
    "제주특별자치도": "제주",
}


def parse_sido_from_name(beopdong_name: str) -> str | None:
    """법정동명에서 시도 부분을 찾아 location_city로 매핑."""
    for full_name, short in SIDO_MAP.items():
        if beopdong_name.startswith(full_name):
            return short
    return None


def extract_location_city_district(
    beopdong_path: str | Path,
    output_path: str | Path,
    encoding: str = "utf-8",
) -> list[dict]:
    """
    법정동코드 파일에서 시도/시군구 레벨만 추출.

    - 시도만 있는 행 (예: 세종특별자치시, 경기도): location_district=""
    - 시군구 있는 행 (예: 서울특별시 구로구, 경기도 안양시 동안구): 둘 다 추출

    출력 스키마: { "location_city": str, "location_district": str, "법정동명_full": str }
    """
    beopdong_path = Path(beopdong_path)
    records: list[dict] = []

    with open(beopdong_path, "r", encoding=encoding) as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n")
            if not line or (i == 0 and line.startswith("법정동코드")):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            code_str, name, status = parts[0], parts[1], parts[2]
            if status != "존재":
                continue
            if len(code_str) != 10 or not code_str.isdigit():
                continue

            # 법정동코드 10자리: AA(시도) BB(시군구) CC(읍면동) DD(리) EE(순번)
            # 시도만: BB=00 (예: 1100000000)
            # 시군구: BB!=00, CC=00 (예: 1111000000 종로구) - 동 단위 제외
            is_sido_only = code_str[2:4] == "00"
            is_sigungu_level = code_str[2:4] != "00" and code_str[4:6] == "00"

            city = parse_sido_from_name(name)
            if not city:
                continue

            if is_sido_only:
                # 시도만 (경기, 세종 등)
                records.append({
                    "location_city": city,
                    "location_district": "",
                    "법정동명_full": name,
                })
            elif is_sigungu_level:
                # 시도 + 시군구 (서울 구로구, 경기 안양시 동안구 등) - 동 단위 제외
                # 법정동명에서 시도 접두어 제거 → 시군구 부분
                for full_sido in SIDO_MAP:
                    if name.startswith(full_sido):
                        district = name[len(full_sido) :].strip()
                        break
                else:
                    district = ""
                records.append({
                    "location_city": city,
                    "location_district": district,
                    "법정동명_full": name,
                })

    # 중복 제거 (동일 city+district 조합)
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for r in records:
        key = (r["location_city"], r["location_district"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    return unique


def load_location_lookup(output_path: str | Path) -> dict:
    """
    추출된 JSON을 로드하여 매칭용 lookup 생성.

    Returns:
        - district_to_city: { "구로구": "서울", "안양시 동안구": "경기", ... }
        - city_districts: { "서울": ["구로구", "강남구", ...], ... }
    """
    with open(output_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    district_to_city: dict[str, str] = {}
    city_districts: dict[str, list[str]] = {}

    for r in records:
        city = r["location_city"]
        district = r["location_district"]
        if district:
            # 동일 구명이 다른 시도에 있을 수 있음 (남구 등) → 시도+구로 키
            district_to_city[f"{city}:{district}"] = city
            district_to_city[district] = city  # 구로만 매칭 (충돌 시 나중 것 사용)
            if city not in city_districts:
                city_districts[city] = []
            if district not in city_districts[city]:
                city_districts[city].append(district)

    return {"district_to_city": district_to_city, "city_districts": city_districts}


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent.parent
    beopdong = base / "data" / "법정동코드 전체자료.txt"
    out = base / "data" / "location_code" / "location_city_district.json"
    result = extract_location_city_district(beopdong, out)
    print(f"Extracted {len(result)} unique location_city/location_district records -> {out}")
