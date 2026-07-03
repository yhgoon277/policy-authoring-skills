"""dev_format_vendor 자기검증 — PI 표 캡처(policy-detail-table 수용) · 골든 샘플 회귀."""
import _toolpath  # noqa: F401
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import dev_format_vendor as dfv

from _toolpath import GOLDEN_HTML

SIMPLE = """<html><body>
<h2>6. 정책 정의</h2><h3>나. 정책 상세</h3>
<h4>1) 유형 정책 (PG-EVT-PROG-001)</h4>
<div class="policy-item">
<div class="policy-item-title">이벤트 유형 정의 (PI-EVT-PROG-001-01)</div>
<span class="policy-item-line">- 유형은 참여형과 비참여형으로 나눈다.<br/></span>
<table class="policy-detail-table"><thead><tr><th>유형</th><th>기준</th></tr></thead>
<tbody><tr><td>참여형</td><td>고객 행동 필요</td></tr></tbody></table>
</div>
</body></html>"""

NESTED = """<html><body>
<h2>6. 정책 정의</h2><h3>나. 정책 상세</h3>
<h4>1) 유형 정책 (PG-EVT-PROG-001)</h4>
<div class="policy-item">
<div class="policy-item-title">이벤트 유형 정의 (PI-EVT-PROG-001-01)</div>
<div class="policy-item-content">
<div class="policy-stmt">- 유형은 참여형과 비참여형으로 나눈다.</div>
<table class="policy-detail-table"><thead><tr><th>유형</th><th>기준</th></tr></thead>
<tbody><tr><td>참여형</td><td>고객 행동 필요</td></tr></tbody></table>
</div></div>
</body></html>"""


class DetailTableCapture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "s.html")
        with open(self.src, "w", encoding="utf-8") as f:
            f.write(SIMPLE)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_policy_detail_table_captured_inside_item(self):
        _, items, _ = dfv.parse_html(Path(self.src))
        it = next(i for i in items if getattr(i, "pi_id", "") == "PI-EVT-PROG-001-01")
        self.assertEqual(len(it.detail_tables or []), 1)
        t0 = it.detail_tables[0]
        self.assertEqual(t0.get("headers"), ["유형", "기준"])
        self.assertEqual(t0.get("rows"), [["참여형", "고객 행동 필요"]])

    def test_generic_tables_still_collected(self):
        tables, _, _ = dfv.parse_html(Path(self.src))
        self.assertTrue(any("policy-detail-table" in (t.table_class or "") for t in tables))

    def test_table_after_inner_div_in_content_still_captured(self):
        # 중첩 수정 가드: content 내부 div(policy-stmt)가 닫혀도 item이 조기 종료되지 않아야 함
        p = os.path.join(self.tmp, "n.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(NESTED)
        _, items, _ = dfv.parse_html(Path(p))
        it = next(i for i in items if getattr(i, "pi_id", "") == "PI-EVT-PROG-001-01")
        self.assertEqual(len(it.detail_tables or []), 1)
        self.assertEqual(it.detail_tables[0].get("headers"), ["유형", "기준"])


@unittest.skipUnless(os.path.exists(GOLDEN_HTML), "골든 샘플 없음")
class GoldenRegression(unittest.TestCase):
    def test_golden_sample_tables_captured(self):
        _, items, _ = dfv.parse_html(Path(GOLDEN_HTML))
        total = sum(len(i.detail_tables or []) for i in items)
        # 원천 policy-detail-table 37개 중 35개가 generic(2개는 policy-detail-subtable).
        # 중첩 깊이 추적 전에는 4개만 캡처됐으나 _pi_content_nest 도입 후 35개 캡처됨(측정값).
        self.assertGreaterEqual(total, 30, "골든 샘플 PI 표가 30개 이상 캡처돼야 함(원천 policy-detail-table 35개 기대)")
