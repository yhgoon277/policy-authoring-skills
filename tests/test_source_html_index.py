"""source_html_index 자기검증 — §6 정책 목록 표(pg_list_names) 파싱."""
import _toolpath  # noqa: F401
import os
import shutil
import tempfile
import unittest

import source_html_index as shi

HTML = """<html><body><h2>6. 정책 정의</h2><h3>가. 정책 목록</h3>
<table class="policy-list-table x"><thead><tr><th>정책 ID</th><th>정책명</th><th>설명</th><th>정책 항목</th></tr></thead>
<tbody><tr><td>PG-EVT-PROG-001</td><td>유형 정책</td><td>설명.</td><td>이벤트 유형 정의<br/>미션 유형 정의</td></tr></tbody></table>
<h3>나. 정책 상세</h3>
<h4>1) 유형 정책 (PG-EVT-PROG-001)</h4>
<div class="policy-item"><div class="policy-item-title">이벤트 유형 정의 (PI-EVT-PROG-001-01)</div></div>
</body></html>"""


class PgListNames(unittest.TestCase):
    def test_list_and_detail_names(self):
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "s.html")
            with open(p, "w", encoding="utf-8") as f:
                f.write(HTML)
            idx = shi.build_index(p)
            self.assertEqual(idx["pg_list_names"].get("PG-EVT-PROG-001"),
                             ["이벤트 유형 정의", "미션 유형 정의"])
            self.assertIn("PG-EVT-PROG-001", idx.get("pg_detail_names", {}))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# full-document 골든 렌더: §5 기능 행이 data-related-pi-ids 속성으로 FN→PI를 명시(주문계약 v0.45).
# 기존 파서는 <tr> 내용(cell)만 읽어 이 속성을 놓쳐 function_to_pis가 비었다(FN_NO_POLICY 오탐 근인).
FN_HTML = """<html><body><h2>5. 기능 정의</h2>
<table class="function-list-table"><thead><tr><th>기능 ID</th><th>기능명</th><th>세부 기능 구성</th></tr></thead>
<tbody>
<tr id="FN-ORD-CUS-001-01-01" data-function-id="FN-ORD-CUS-001-01-01" data-related-pi-ids="PI-ORD-ENTRY-001-001,PI-ORD-ENTRY-001-002"><td class="mono">FN-ORD-CUS-001-01-01</td><td>진입 식별</td><td>세부A</td></tr>
<tr id="FN-ORD-COM-001-01" data-function-id="FN-ORD-COM-001-01" data-related-pi-ids="PI-ORD-AUTH-001-001"><td class="mono">FN-ORD-COM-001-01</td><td>인증 판단</td><td>세부B</td></tr>
</tbody></table>
</body></html>"""


class FunctionRelatedPi(unittest.TestCase):
    def _idx(self):
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "fn.html")
            with open(p, "w", encoding="utf-8") as f:
                f.write(FN_HTML)
            return shi.build_index(p)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fn_to_pis_from_data_attribute(self):
        idx = self._idx()
        self.assertEqual(idx["function_to_pis"].get("FN-ORD-CUS-001-01-01"),
                         ["PI-ORD-ENTRY-001-001", "PI-ORD-ENTRY-001-002"])
        self.assertEqual(idx["function_to_pis"].get("FN-ORD-COM-001-01"),
                         ["PI-ORD-AUTH-001-001"])
