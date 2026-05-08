import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dividend_alert as da

FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures"


class DividendAlertTests(unittest.TestCase):
    def test_parse_dividend_fields_happy_path(self):
        cells = [""] * 24
        cells[8] = "372"
        cells[19] = "2,453,315,636,604"
        cells[21] = "2026-03-31"
        cells[23] = "2026-05-29"

        per_share, total_dividend, record_date, payment_date = da.parse_dividend_fields(cells)

        self.assertEqual(per_share, "372")
        self.assertEqual(total_dividend, "2,453,315,636,604")
        self.assertEqual(record_date, "2026-03-31")
        self.assertEqual(payment_date, "2026-05-29")

    def test_parse_dividend_fields_missing_payment_date(self):
        cells = [""] * 24
        cells[8] = "375"
        cells[19] = "265,764,625,500"
        cells[21] = "2026-05-31"
        cells[23] = "-"

        per_share, total_dividend, record_date, payment_date = da.parse_dividend_fields(cells)

        self.assertEqual(per_share, "375")
        self.assertIsNone(payment_date)

    def test_compute_status_initial(self):
        self.assertEqual(da.compute_status(None, "20260430800106", "372"), "초기 수집")

    def test_compute_status_changed_receipt(self):
        prev = {"receipt_no": "old", "dividend_per_share": "372"}
        self.assertEqual(da.compute_status(prev, "new", "372"), "변동 있음")

    def test_compute_status_changed_dividend(self):
        prev = {"receipt_no": "same", "dividend_per_share": "372"}
        self.assertEqual(da.compute_status(prev, "same", "400"), "변동 있음")

    def test_compute_status_unchanged(self):
        prev = {"receipt_no": "same", "dividend_per_share": "372"}
        self.assertEqual(da.compute_status(prev, "same", "372"), "변동 없음")

    def test_build_message_contains_core_fields(self):
        item = da.DividendInfo(
            name="삼성전자",
            stock_code="005930",
            corp_code="00126380",
            receipt_no="20260430800106",
            disclosure_date="2026-04-30",
            report_name="현금ㆍ현물배당결정",
            dividend_per_share="372",
            total_dividend="2,453,315,636,604",
            record_date="2026-03-31",
            payment_date="2026-05-29",
            status="변동 있음",
            changes=["접수번호: old → new"],
        )
        message = da.build_message([item])
        self.assertIn("삼성전자 (005930)", message)
        self.assertIn("1주당 분배금: 372원", message)
        self.assertIn("상태: 변동 있음", message)
        self.assertIn("지급예정일: 2026-05-29", message)
        self.assertIn("변경사항: 접수번호: old → new", message)
        self.assertIn("일부 종목 조회에 실패해도", message)

    def test_build_message_compact_when_all_unchanged(self):
        items = [
            da.DividendInfo(
                name="삼성전자",
                stock_code="005930",
                corp_code="00126380",
                receipt_no="1",
                disclosure_date="2026-04-30",
                report_name="현금ㆍ현물배당결정",
                dividend_per_share="372",
                total_dividend="1",
                record_date="2026-03-31",
                payment_date="2026-05-29",
                status="변동 없음",
            ),
            da.DividendInfo(
                name="현대차",
                stock_code="005380",
                corp_code="00164742",
                receipt_no="2",
                disclosure_date="2026-04-23",
                report_name="현금ㆍ현물배당결정",
                dividend_per_share="2,500",
                total_dividend="2",
                record_date="2026-05-31",
                payment_date="2026-06-30",
                status="변동 없음",
            ),
        ]
        message = da.build_message(items)
        self.assertIn("삼성전자: 변동 없음 / 최근 분배금 372원 / 최근 공시일 2026-04-30", message)
        self.assertIn("현대차: 변동 없음 / 최근 분배금 2,500원 / 최근 공시일 2026-04-23", message)
        self.assertNotIn("접수번호", message)
        self.assertNotIn("배당기준일", message)

    def test_build_change_list_detects_field_diffs(self):
        prev = {
            "receipt_no": "20260401000001",
            "disclosure_date": "2026-04-01",
            "dividend_per_share": "372",
            "total_dividend": "2,000",
            "record_date": "2026-03-31",
            "payment_date": None,
        }
        current = da.DividendInfo(
            name="삼성전자",
            stock_code="005930",
            corp_code="00126380",
            receipt_no="20260430800106",
            disclosure_date="2026-04-30",
            report_name="현금ㆍ현물배당결정",
            dividend_per_share="400",
            total_dividend="2,500",
            record_date="2026-04-30",
            payment_date="2026-05-29",
            status="변동 있음",
        )
        changes = da.build_change_list(prev, current)
        self.assertIn("접수번호: 20260401000001 → 20260430800106", changes)
        self.assertIn("공시일: 2026-04-01 → 2026-04-30", changes)
        self.assertIn("1주당 분배금: 372원 → 400원", changes)
        self.assertIn("배당금총액: 2,000원 → 2,500원", changes)
        self.assertIn("배당기준일: 2026-03-31 → 2026-04-30", changes)
        self.assertIn("지급예정일: 없음 → 2026-05-29", changes)

    def test_build_message_shows_error_details(self):
        item = da.DividendInfo(
            name="현대차",
            stock_code="005380",
            corp_code="00164742",
            receipt_no="-",
            disclosure_date="-",
            report_name="-",
            dividend_per_share=None,
            total_dividend=None,
            record_date=None,
            payment_date=None,
            status="조회 실패",
            error="OpenDART timeout",
        )
        message = da.build_message([item])
        self.assertIn("상태: 조회 실패", message)
        self.assertIn("조회 결과: 실패", message)
        self.assertIn("오류: OpenDART timeout", message)

    def test_load_env_reads_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("FOO=bar\nHELLO=world\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True):
                da.load_env(env_path)
                self.assertEqual(os.environ.get("FOO"), "bar")
                self.assertEqual(os.environ.get("HELLO"), "world")

    def test_load_config_reads_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({
                "timezone": "Asia/Seoul",
                "schedule": {"time": "07:30"},
                "email": {"recipients": ["a@example.com", "b@example.com"]},
                "stocks": [{"name": "삼성전자", "stock_code": "005930", "corp_code": "00126380"}],
            }, ensure_ascii=False), encoding="utf-8")
            config = da.load_config(config_path)
            self.assertEqual(config["timezone"], "Asia/Seoul")
            self.assertEqual(config["schedule"]["time"], "07:30")
            self.assertEqual(config["email"]["recipients"], ["a@example.com", "b@example.com"])

    def test_save_and_load_state_roundtrip(self):
        item = da.DividendInfo(
            name="현대차",
            stock_code="005380",
            corp_code="00164742",
            receipt_no="20260423800359",
            disclosure_date="2026-04-23",
            report_name="현금ㆍ현물배당결정",
            dividend_per_share="2500",
            total_dividend="654,585,190,000",
            record_date="2026-05-31",
            payment_date="2026-06-30",
            status="초기 수집",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            state_file = state_dir / "latest.json"
            with mock.patch.object(da, "STATE_DIR", state_dir), mock.patch.object(da, "STATE_FILE", state_file):
                da.save_state([item])
                loaded = da.load_state()
                self.assertEqual(loaded["현대차"]["receipt_no"], "20260423800359")
                self.assertEqual(loaded["현대차"]["dividend_per_share"], "2500")

    def test_parse_dividend_fields_from_real_samsung_fixture(self):
        html = (FIXTURES / "samsung_20260430800106.html").read_text(encoding="utf-8")
        parser = da.TDParser()
        parser.feed(html)
        per_share, total_dividend, record_date, payment_date = da.parse_dividend_fields(parser.cells)
        self.assertEqual(per_share, "372")
        self.assertEqual(total_dividend, "2,453,315,636,604")
        self.assertEqual(record_date, "2026-03-31")
        self.assertEqual(payment_date, "2026-05-29")

    def test_parse_dividend_fields_from_real_skhynix_fixture(self):
        html = (FIXTURES / "skhynix_20260422800788.html").read_text(encoding="utf-8")
        parser = da.TDParser()
        parser.feed(html)
        per_share, total_dividend, record_date, payment_date = da.parse_dividend_fields(parser.cells)
        self.assertEqual(per_share, "375")
        self.assertEqual(total_dividend, "265,764,625,500")
        self.assertEqual(record_date, "2026-05-31")
        self.assertIsNone(payment_date)

    def test_parse_dividend_fields_from_real_hyundai_fixture(self):
        html = (FIXTURES / "hyundai_20260423800359.html").read_text(encoding="utf-8")
        parser = da.TDParser()
        parser.feed(html)
        per_share, total_dividend, record_date, payment_date = da.parse_dividend_fields(parser.cells)
        self.assertEqual(per_share, "2,500")
        self.assertEqual(total_dividend, "654,585,190,000")
        self.assertEqual(record_date, "2026-05-31")
        self.assertEqual(payment_date, "2026-06-30")

    def test_configurable_recipients_stocks_and_schedule_are_applied(self):
        fake_config = {
            "timezone": "Asia/Seoul",
            "schedule": {"time": "08:45"},
            "email": {"recipients": ["alpha@example.com", "beta@example.com"]},
            "stocks": [
                {"name": "삼성전자", "stock_code": "005930", "corp_code": "00126380"},
                {"name": "현대차", "stock_code": "005380", "corp_code": "00164742"},
            ],
        }

        disclosures = {
            "삼성전자": {"rcept_no": "20260430800106", "rcept_dt": "20260430", "report_nm": "현금ㆍ현물배당결정"},
            "현대차": {"rcept_no": "20260423800359", "rcept_dt": "20260423", "report_nm": "현금ㆍ현물배당결정"},
        }

        cells_by_receipt = {
            "20260430800106": [""] * 24,
            "20260423800359": [""] * 24,
        }
        cells_by_receipt["20260430800106"][8] = "372"
        cells_by_receipt["20260430800106"][19] = "2,453,315,636,604"
        cells_by_receipt["20260430800106"][21] = "2026-03-31"
        cells_by_receipt["20260430800106"][23] = "2026-05-29"

        cells_by_receipt["20260423800359"][8] = "2,500"
        cells_by_receipt["20260423800359"][19] = "654,585,190,000"
        cells_by_receipt["20260423800359"][21] = "2026-05-31"
        cells_by_receipt["20260423800359"][23] = "2026-06-30"

        sent = {}

        def fake_fetch_latest(api_key, company):
            return disclosures[company["name"]]

        def fake_fetch_cells(api_key, receipt_no):
            return cells_by_receipt[receipt_no]

        def fake_send_gmail(to, subject, body):
            sent["to"] = to
            sent["subject"] = subject
            sent["body"] = body

        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            state_file = state_dir / "latest.json"
            with mock.patch.object(da, "load_config", return_value=fake_config), \
                 mock.patch.object(da, "load_state", return_value={}), \
                 mock.patch.object(da, "fetch_latest_dividend_disclosure", side_effect=fake_fetch_latest), \
                 mock.patch.object(da, "fetch_document_cells", side_effect=fake_fetch_cells), \
                 mock.patch.object(da, "send_gmail", side_effect=fake_send_gmail), \
                 mock.patch.object(da, "STATE_DIR", state_dir), \
                 mock.patch.object(da, "STATE_FILE", state_file), \
                 mock.patch.dict(os.environ, {"OPENDART_API_KEY": "test-key"}, clear=True), \
                 mock.patch("sys.argv", ["dividend_alert.py"]):
                da.main()

        self.assertEqual(sent["to"], "alpha@example.com,beta@example.com")
        self.assertIn("삼성전자/현대차", sent["subject"])
        self.assertIn("삼성전자 (005930)", sent["body"])
        self.assertIn("현대차 (005380)", sent["body"])
        self.assertNotIn("SK하이닉스", sent["body"])


if __name__ == "__main__":
    unittest.main()
