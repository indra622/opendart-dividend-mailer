import tempfile
import unittest
from pathlib import Path
from unittest import mock

import stock_lookup as sl


SAMPLE_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<result>
  <list>
    <corp_code>00126380</corp_code>
    <corp_name>삼성전자</corp_name>
    <stock_code>005930</stock_code>
    <modify_date>20260401</modify_date>
  </list>
  <list>
    <corp_code>00164779</corp_code>
    <corp_name>SK하이닉스</corp_name>
    <stock_code>000660</stock_code>
    <modify_date>20260401</modify_date>
  </list>
  <list>
    <corp_code>00999999</corp_code>
    <corp_name>비상장회사</corp_name>
    <stock_code> </stock_code>
    <modify_date>20260401</modify_date>
  </list>
</result>
"""


class StockLookupTests(unittest.TestCase):
    def test_parse_corp_code_xml_keeps_listed_companies_only(self):
        companies = sl.parse_corp_code_xml(SAMPLE_XML)
        self.assertEqual(len(companies), 2)
        self.assertEqual(companies[0]["corp_name"], "삼성전자")
        self.assertEqual(companies[0]["stock_code"], "005930")
        self.assertEqual(companies[0]["corp_code"], "00126380")

    def test_search_by_exact_name(self):
        companies = sl.parse_corp_code_xml(SAMPLE_XML)
        results = sl.search_companies("삼성전자", companies)
        self.assertEqual(results[0]["stock_code"], "005930")
        self.assertEqual(results[0]["corp_code"], "00126380")

    def test_search_by_partial_name_ignores_spaces_and_case(self):
        companies = sl.parse_corp_code_xml(SAMPLE_XML)
        results = sl.search_companies("sk 하이", companies)
        self.assertEqual(results[0]["corp_name"], "SK하이닉스")

    def test_search_by_stock_code(self):
        companies = sl.parse_corp_code_xml(SAMPLE_XML)
        results = sl.search_companies("000660", companies)
        self.assertEqual(results[0]["corp_name"], "SK하이닉스")

    def test_cache_roundtrip(self):
        companies = sl.parse_corp_code_xml(SAMPLE_XML)
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "corp_codes.json"
            sl.save_cached_corp_codes(companies, cache_file)
            loaded = sl.load_cached_corp_codes(cache_file)
        self.assertEqual(loaded, companies)

    def test_get_corp_codes_uses_cache_without_api_key(self):
        companies = sl.parse_corp_code_xml(SAMPLE_XML)
        with mock.patch.object(sl, "load_cached_corp_codes", return_value=companies), \
             mock.patch.object(sl, "fetch_corp_codes") as fetch:
            loaded = sl.get_corp_codes(refresh=False)
        self.assertEqual(loaded, companies)
        fetch.assert_not_called()

    def test_opendart_error_message_from_xml_response(self):
        raw = '<?xml version="1.0"?><result><status>010</status><message>등록되지 않은 인증키입니다.</message></result>'.encode()
        self.assertEqual(sl.opendart_error_message(raw), "OpenDART error 010: 등록되지 않은 인증키입니다.")


if __name__ == "__main__":
    unittest.main()
