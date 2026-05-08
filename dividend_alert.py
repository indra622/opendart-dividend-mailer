#!/usr/bin/env python3
import io
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "latest.json"
ENV_FILE = ROOT / ".env"
CONFIG_FILE = ROOT / "config.json"
DEFAULT_TIMEZONE = "Asia/Seoul"


class TDParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_td = False
        self.text = ""
        self.cells = []

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self.in_td = True
            self.text = ""

    def handle_endtag(self, tag):
        if tag == "td" and self.in_td:
            self.cells.append(" ".join(self.text.split()))
            self.in_td = False

    def handle_data(self, data):
        if self.in_td:
            self.text += data


@dataclass
class DividendInfo:
    name: str
    stock_code: str
    corp_code: str
    receipt_no: str
    disclosure_date: str
    report_name: str
    dividend_per_share: str | None
    total_dividend: str | None
    record_date: str | None
    payment_date: str | None
    status: str
    error: str | None = None
    changes: list[str] | None = None


def load_env(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def load_config(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"Missing config file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env: {name}")
    return value


def http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_latest_dividend_disclosure(api_key: str, company: dict) -> dict:
    params = urllib.parse.urlencode({
        "crtfc_key": api_key,
        "corp_code": company["corp_code"],
        "bgn_de": "20200101",
        "end_de": datetime.now().strftime("%Y%m%d"),
        "page_count": "100",
    })
    url = f"https://opendart.fss.or.kr/api/list.json?{params}"
    data = http_get_json(url)
    if data.get("status") != "000":
        raise RuntimeError(f"OpenDART list error for {company['name']}: {data}")
    hits = [x for x in data.get("list", []) if "현금ㆍ현물배당결정" in x.get("report_nm", "")]
    if not hits:
        raise RuntimeError(f"No dividend disclosure found for {company['name']}")
    latest = sorted(hits, key=lambda x: x["rcept_dt"], reverse=True)[0]
    return latest


def fetch_document_cells(api_key: str, receipt_no: str) -> list[str]:
    params = urllib.parse.urlencode({"crtfc_key": api_key, "rcept_no": receipt_no})
    url = f"https://opendart.fss.or.kr/api/document.xml?{params}"
    raw = urllib.request.urlopen(url, timeout=30).read()
    zf = zipfile.ZipFile(io.BytesIO(raw))
    name = zf.namelist()[0]
    html = zf.read(name).decode("euc-kr", errors="ignore")
    parser = TDParser()
    parser.feed(html)
    return parser.cells


def _looks_like_money(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9][0-9,]*", value))


def _looks_like_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def parse_dividend_fields(cells: list[str]) -> tuple[str | None, str | None, str | None, str | None]:
    # 현재 확보한 실제 공시 fixture 기준으로 테이블 구조가 동일하다.
    # 따라서 필요한 위치를 인덱스로 뽑되, 값 패턴을 검증해서 구조가 달라지면 조용히 틀린 값을 내지 않게 한다.
    if len(cells) < 24:
        raise RuntimeError(f"Unexpected disclosure table length: {len(cells)}")

    per_share = cells[8]
    total_dividend = cells[19]
    record_date = cells[21]
    payment_date = cells[23]

    if not _looks_like_money(per_share):
        raise RuntimeError(f"Failed to parse per-share dividend from cell[8]: {per_share!r}")
    if not _looks_like_money(total_dividend):
        raise RuntimeError(f"Failed to parse total dividend from cell[19]: {total_dividend!r}")
    if not _looks_like_date(record_date):
        raise RuntimeError(f"Failed to parse record date from cell[21]: {record_date!r}")
    if payment_date != "-" and not _looks_like_date(payment_date):
        raise RuntimeError(f"Failed to parse payment date from cell[23]: {payment_date!r}")

    if payment_date == "-":
        payment_date = None
    return per_share, total_dividend, record_date, payment_date


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(items: list[DividendInfo]):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        item.name: {
            "stock_code": item.stock_code,
            "corp_code": item.corp_code,
            "receipt_no": item.receipt_no,
            "disclosure_date": item.disclosure_date,
            "report_name": item.report_name,
            "dividend_per_share": item.dividend_per_share,
            "total_dividend": item.total_dividend,
            "record_date": item.record_date,
            "payment_date": item.payment_date,
        }
        for item in items
    }
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_change_list(prev: dict | None, current: DividendInfo) -> list[str]:
    if not prev:
        return ["최초 수집된 기준값입니다."]

    changes = []
    field_specs = [
        ("receipt_no", "접수번호"),
        ("disclosure_date", "공시일"),
        ("dividend_per_share", "1주당 분배금"),
        ("total_dividend", "배당금총액"),
        ("record_date", "배당기준일"),
        ("payment_date", "지급예정일"),
    ]
    for field, label in field_specs:
        old = prev.get(field)
        new = getattr(current, field)
        if old != new:
            old_text = old if old not in (None, "") else "없음"
            new_text = new if new not in (None, "") else "없음"
            suffix = "원" if field in ("dividend_per_share", "total_dividend") and new_text != "없음" else ""
            old_suffix = "원" if field in ("dividend_per_share", "total_dividend") and old_text != "없음" else ""
            changes.append(f"{label}: {old_text}{old_suffix} → {new_text}{suffix}")
    return changes


def compute_status(prev: dict | None, current_receipt_no: str, current_dividend: str | None) -> str:
    if not prev:
        return "초기 수집"
    if prev.get("receipt_no") != current_receipt_no:
        return "변동 있음"
    if prev.get("dividend_per_share") != current_dividend:
        return "변동 있음"
    return "변동 없음"


def should_render_compact(items: list[DividendInfo]) -> bool:
    return all((item.status == "변동 없음" and not item.error) for item in items)


def build_message(items: list[DividendInfo]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"배당 현황 - {now}", ""]

    if should_render_compact(items):
        for item in items:
            lines.append(
                f"- {item.name}: 변동 없음 / 최근 분배금 {item.dividend_per_share or '확인 필요'}원 / 최근 공시일 {item.disclosure_date}"
            )
        lines.append("")
        lines.append("※ 새 공시가 없으면 가장 최근 공시 기준 금액을 유지합니다.")
        return "\n".join(lines)

    for item in items:
        lines.append(f"- {item.name} ({item.stock_code})")
        lines.append(f"  - 상태: {item.status}")
        if item.error:
            lines.append(f"  - 조회 결과: 실패")
            lines.append(f"  - 오류: {item.error}")
        else:
            if item.changes:
                for change in item.changes:
                    lines.append(f"  - 변경사항: {change}")
            lines.append(f"  - 1주당 분배금: {item.dividend_per_share or '확인 필요'}원" if item.dividend_per_share else "  - 1주당 분배금: 확인 필요")
            lines.append(f"  - 배당금총액: {item.total_dividend or '확인 필요'}원" if item.total_dividend else "  - 배당금총액: 확인 필요")
            lines.append(f"  - 최근 공시일: {item.disclosure_date}")
            lines.append(f"  - 배당기준일: {item.record_date or '확인 필요'}")
            lines.append(f"  - 지급예정일: {item.payment_date or '미정'}")
            lines.append(f"  - 공시명: {item.report_name}")
            lines.append(f"  - 접수번호: {item.receipt_no}")
        lines.append("")
    lines.append("※ 새 공시가 없으면 가장 최근 공시 기준 금액을 유지합니다.")
    lines.append("※ 일부 종목 조회에 실패해도 나머지 종목은 계속 발송합니다.")
    return "\n".join(lines)


def send_gmail(to: str, subject: str, body: str):
    cmd = [
        "gws", "gmail", "+send",
        "--to", to,
        "--subject", subject,
        "--body", body,
    ]
    subprocess.run(cmd, check=True)


def main():
    load_env(ENV_FILE)
    config = load_config(CONFIG_FILE)
    api_key = require_env("OPENDART_API_KEY")
    recipients = config.get("email", {}).get("recipients", [])
    companies = config.get("stocks", [])
    timezone = config.get("timezone", DEFAULT_TIMEZONE)
    schedule_time = config.get("schedule", {}).get("time", "07:30")
    if not recipients:
        raise RuntimeError("No email recipients configured in config.json")
    if not companies:
        raise RuntimeError("No stocks configured in config.json")
    prev_state = load_state()
    items: list[DividendInfo] = []
    for company in companies:
        try:
            latest = fetch_latest_dividend_disclosure(api_key, company)
            cells = fetch_document_cells(api_key, latest["rcept_no"])
            per_share, total_dividend, record_date, payment_date = parse_dividend_fields(cells)
            status = compute_status(prev_state.get(company["name"]), latest["rcept_no"], per_share)
            current = DividendInfo(
                name=company["name"],
                stock_code=company["stock_code"],
                corp_code=company["corp_code"],
                receipt_no=latest["rcept_no"],
                disclosure_date=f"{latest['rcept_dt'][0:4]}-{latest['rcept_dt'][4:6]}-{latest['rcept_dt'][6:8]}",
                report_name=latest["report_nm"].strip(),
                dividend_per_share=per_share,
                total_dividend=total_dividend,
                record_date=record_date,
                payment_date=payment_date,
                status=status,
            )
            current.changes = build_change_list(prev_state.get(company["name"]), current)
            items.append(current)
        except Exception as e:
            items.append(DividendInfo(
                name=company["name"],
                stock_code=company["stock_code"],
                corp_code=company["corp_code"],
                receipt_no="-",
                disclosure_date="-",
                report_name="-",
                dividend_per_share=None,
                total_dividend=None,
                record_date=None,
                payment_date=None,
                status="조회 실패",
                error=str(e),
            ))
    message = build_message(items)
    stock_names = "/".join([company["name"] for company in companies])
    subject = f"[배당 알림] {datetime.now().strftime('%Y-%m-%d')} {stock_names}"
    if "--print-only" in sys.argv:
        print(message)
        print(f"\n[config] timezone={timezone}, schedule={schedule_time}, recipients={', '.join(recipients)}")
    else:
        send_gmail(",".join(recipients), subject, message)
        print(message)
    save_state([item for item in items if not item.error])


if __name__ == "__main__":
    main()
