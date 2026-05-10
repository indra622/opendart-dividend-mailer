#!/usr/bin/env python3
"""Find OpenDART stock_code and corp_code by company name.

Usage:
    python3 stock_lookup.py 삼성전자
    python3 stock_lookup.py NAVER --json
"""

import argparse
import io
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
CACHE_DIR = ROOT / "state"
CACHE_FILE = CACHE_DIR / "corp_codes.json"
OPENDART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
COMMON_CA_FILES = [
    Path("/etc/ssl/cert.pem"),
    Path("/opt/homebrew/etc/openssl@3/cert.pem"),
]


def default_ssl_context() -> ssl.SSLContext | None:
    for cafile in COMMON_CA_FILES:
        if cafile.exists():
            return ssl.create_default_context(cafile=str(cafile))
    return None


def load_env(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def require_api_key() -> str:
    api_key = os.environ.get("OPENDART_API_KEY")
    if not api_key:
        raise RuntimeError("Missing required env: OPENDART_API_KEY")
    return api_key


def normalize(text: str) -> str:
    return "".join(text.lower().split())


def parse_corp_code_xml(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    companies = []
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        if not stock_code:
            # OpenDART also contains non-listed companies. This project needs listed stocks only.
            continue
        companies.append({
            "corp_code": (item.findtext("corp_code") or "").strip(),
            "corp_name": (item.findtext("corp_name") or "").strip(),
            "stock_code": stock_code,
            "modify_date": (item.findtext("modify_date") or "").strip(),
        })
    return companies


def opendart_error_message(raw: bytes) -> str | None:
    if raw.startswith(b"PK"):
        return None
    try:
        root = ET.fromstring(raw.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return "OpenDART 응답이 ZIP/XML 형식이 아닙니다."
    status = root.findtext("status") or "unknown"
    message = root.findtext("message") or "알 수 없는 오류"
    return f"OpenDART error {status}: {message}"


def fetch_corp_codes(api_key: str) -> list[dict[str, str]]:
    query = urllib.parse.urlencode({"crtfc_key": api_key})
    with urllib.request.urlopen(f"{OPENDART_CORP_CODE_URL}?{query}", timeout=30, context=default_ssl_context()) as response:
        raw = response.read()

    error = opendart_error_message(raw)
    if error:
        raise RuntimeError(error)

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml_name = zf.namelist()[0]
        xml_text = zf.read(xml_name).decode("utf-8")
    return parse_corp_code_xml(xml_text)


def load_cached_corp_codes(cache_file: Path = CACHE_FILE) -> list[dict[str, str]] | None:
    if not cache_file.exists():
        return None
    return json.loads(cache_file.read_text(encoding="utf-8"))


def save_cached_corp_codes(companies: list[dict[str, str]], cache_file: Path = CACHE_FILE) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(companies, ensure_ascii=False, indent=2), encoding="utf-8")


def get_corp_codes(refresh: bool = False) -> list[dict[str, str]]:
    if not refresh:
        cached = load_cached_corp_codes()
        if cached is not None:
            return cached

    load_env()
    companies = fetch_corp_codes(require_api_key())
    save_cached_corp_codes(companies)
    return companies


def search_companies(query: str, companies: list[dict[str, str]], limit: int = 10) -> list[dict[str, str]]:
    q = normalize(query)
    exact = []
    prefix = []
    contains = []
    code_matches = []

    for company in companies:
        name = company["corp_name"]
        code = company["stock_code"]
        normalized_name = normalize(name)
        if q == normalize(code):
            code_matches.append(company)
        elif q == normalized_name:
            exact.append(company)
        elif normalized_name.startswith(q):
            prefix.append(company)
        elif q in normalized_name:
            contains.append(company)

    # Preserve useful order: exact > stock code > prefix > contains.
    results = exact + code_matches + prefix + contains
    deduped = []
    seen = set()
    for item in results:
        key = (item["corp_code"], item["stock_code"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def print_text_results(query: str, results: list[dict[str, str]]) -> None:
    if not results:
        print(f"검색 결과가 없습니다: {query}")
        print("회사명을 줄여서 다시 검색해보세요. 예: 삼성, 현대차, NAVER")
        return

    print(f"검색어: {query}")
    for idx, item in enumerate(results, start=1):
        print(f"{idx}. {item['corp_name']}")
        print(f"   stock_code: {item['stock_code']}")
        print(f"   corp_code : {item['corp_code']}")
        if item.get("modify_date"):
            print(f"   기준일    : {item['modify_date']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="종목명으로 stock_code와 OpenDART corp_code를 찾습니다.")
    parser.add_argument("query", help="검색할 종목명 또는 6자리 종목코드. 예: 삼성전자, 005930")
    parser.add_argument("--limit", type=int, default=10, help="표시할 최대 검색 결과 수")
    parser.add_argument("--refresh", action="store_true", help="캐시를 무시하고 OpenDART 회사고유번호 목록을 다시 받기")
    parser.add_argument("--json", action="store_true", help="검색 결과를 JSON으로 출력")
    args = parser.parse_args(argv)

    try:
        companies = get_corp_codes(refresh=args.refresh)
        results = search_companies(args.query, companies, limit=args.limit)
    except Exception as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_text_results(args.query, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
