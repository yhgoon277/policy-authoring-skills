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
