"""rebuild_policy_from_source 자기검증 — 원천 §6 정책 목록 표 '설명' → PG description(원천 정본 우선)."""
import _toolpath  # noqa: F401
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import rebuild_policy_from_source as rb


def cell(text="", ids=()):
    return NS(text=text, ids=list(ids))


def pl_table(pg, desc):
    return NS(table_class="policy-list-table", headers=["정책 ID", "정책명", "설명", "정책 항목"],
              rows=[[cell(pg, [pg]), cell("이름"), cell(desc), cell("항목")]])


class PgDescExtract(unittest.TestCase):
    def test_extracts_pg_description(self):
        out = rb._pg_desc_from_tables([pl_table("PG-EVT-PROG-001", "유형 구분 기준.")])
        self.assertEqual(out, {"PG-EVT-PROG-001": "유형 구분 기준."})

    def test_first_description_wins_on_repeat(self):
        # 같은 PG가 프로세스별 정책 목록 표에 반복 등장(실측 21개 표) — 첫 설명 유지
        out = rb._pg_desc_from_tables([pl_table("PG-EVT-A-001", "첫 설명"), pl_table("PG-EVT-A-001", "뒷 설명")])
        self.assertEqual(out["PG-EVT-A-001"], "첫 설명")

    def test_ignores_non_policy_tables(self):
        t = NS(table_class="", headers=["기능 ID", "기능명", "설명"],
               rows=[[cell("FN-EVT-001", ["FN-EVT-001"]), cell("n"), cell("d")]])
        self.assertEqual(rb._pg_desc_from_tables([t]), {})


class RebuildWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src.html")
        with open(self.src, "w", encoding="utf-8") as f:
            f.write("<h4>1) 프로그램 유형 구분 정책 (PG-EVT-PROG-001)</h4>")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _item():
        return NS(pi_id="PI-EVT-PROG-001-01", pg_id="PG-EVT-PROG-001", name="이벤트 유형 정의",
                  content="", rules=[], detail_tables=[])

    def test_source_description_wins_over_empty_spec(self):
        tables = [pl_table("PG-EVT-PROG-001", "원천 설명.")]
        spec = {"policy_details": [],
                "policy_groups": [{"id": "PG-EVT-PROG-001", "name": "", "description": ""}]}
        with patch.object(rb.dfv, "parse_html", return_value=(tables, [self._item()], None)):
            out = rb.rebuild(spec, self.src)
        self.assertEqual(out["policy_groups"][0]["description"], "원천 설명.")

    def test_spec_description_kept_when_source_lacks(self):
        spec = {"policy_details": [],
                "policy_groups": [{"id": "PG-EVT-PROG-001", "name": "n", "description": "기존 설명"}]}
        with patch.object(rb.dfv, "parse_html", return_value=([], [self._item()], None)):
            out = rb.rebuild(spec, self.src)
        self.assertEqual(out["policy_groups"][0]["description"], "기존 설명")


if __name__ == "__main__":
    unittest.main()
