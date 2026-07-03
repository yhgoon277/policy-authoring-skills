"""render_preview 자기검증 — §6 정책 상세: criteria(원천 불릿)와 detail_tables 동시 렌더."""
import _toolpath  # noqa: F401
import unittest

import render_preview as rp


def _render(pi):
    spec = {"meta": {}, "policy_groups": [{"id": "PG-EVT-A-001", "name": "그룹", "description": "",
                                           "items": [{"id": pi["id"], "name": pi["name"]}]}],
            "policy_details": [pi], "processes": [], "functions": [], "function_details": [],
            "use_cases": [], "process_relations": []}
    return rp.render_policy_details(spec)


class CriteriaWithTables(unittest.TestCase):
    def test_criteria_bullets_render_alongside_tables(self):
        html = _render({"id": "PI-EVT-A-001-01", "name": "항목", "group_id": "PG-EVT-A-001",
                        "rule_statement": "문장.", "criteria": ["기준 하나", "기준 둘"],
                        "detail_tables": [{"headers": ["h"], "rows": [["v"]]}]})
        self.assertIn("policy-criteria", html)          # 불릿 렌더됨(표 있어도)
        self.assertIn("기준 하나", html)
        self.assertIn("policy-detail-table", html)      # 표도 렌더
        # 순서: 불릿이 표보다 앞
        self.assertLess(html.index("policy-criteria"), html.index("policy-detail-table"))

    def test_legacy_criteria_values_still_suppressed_by_tables(self):
        html = _render({"id": "PI-EVT-A-001-01", "name": "항목", "group_id": "PG-EVT-A-001",
                        "rule_statement": "문장.", "criteria_values": ["표와 중복 기술"],
                        "detail_tables": [{"headers": ["h"], "rows": [["v"]]}]})
        self.assertNotIn("표와 중복 기술", html)         # 레거시 중복 억제 유지

    def test_criteria_values_render_without_tables(self):
        html = _render({"id": "PI-EVT-A-001-01", "name": "항목", "group_id": "PG-EVT-A-001",
                        "rule_statement": "문장.", "criteria_values": ["값 기준"]})
        self.assertIn("값 기준", html)
