"""T-R4 오라클 자기검증 — 최종 JSON↔HTML 정합(선언 엔티티가 HTML에 빠짐없이 렌더됐는가)."""
import _toolpath  # noqa: F401
import unittest
from unittest.mock import patch

import completion_audit as ca


def html_idx(fns=(), pgs_pis=None):
    return {"process_to_functions": {}, "process_to_policy_groups": {},
            "function_to_subfns": {f: [] for f in fns}, "function_to_pis": {},
            "pg_to_pis": pgs_pis or {}, "function_names": {}, "function_descriptions": {}}


class Base(unittest.TestCase):
    def setUp(self):
        self.idx = html_idx()
        self.patcher = patch.object(ca.shi, "build_index", side_effect=lambda p: self.idx)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    @staticmethod
    def invs(r):
        return {f["invariant"] for f in r["findings"]}


class Consistency(Base):
    def test_pass(self):
        self.idx = html_idx(fns=["FN-PAY-001"], pgs_pis={"PG-PAY-001": ["PI-PAY-001"]})
        spec = {"functions": [{"id": "FN-PAY-001"}], "policy_groups": [{"id": "PG-PAY-001"}],
                "policy_details": [{"id": "PI-PAY-001"}]}
        r = ca.audit(spec, "dummy.html")
        self.assertEqual(r["verdict"], "PASS")

    def test_missing_function(self):
        self.idx = html_idx(fns=["FN-PAY-001"])
        spec = {"functions": [{"id": "FN-PAY-001"}, {"id": "FN-PAY-002"}]}
        r = ca.audit(spec, "dummy.html")
        self.assertIn("C_FN_COUNT", self.invs(r))
        self.assertEqual(r["verdict"], "FAIL")

    def test_missing_policy_group(self):
        self.idx = html_idx(pgs_pis={"PG-PAY-001": ["PI-PAY-001"]})
        spec = {"policy_groups": [{"id": "PG-PAY-001"}, {"id": "PG-PAY-002"}]}
        r = ca.audit(spec, "dummy.html")
        self.assertIn("C_PG_COVERAGE", self.invs(r))
        self.assertEqual(r["verdict"], "FAIL")

    def test_missing_policy_item(self):
        self.idx = html_idx(pgs_pis={"PG-PAY-001": ["PI-PAY-001"]})
        spec = {"policy_groups": [{"id": "PG-PAY-001"}],
                "policy_details": [{"id": "PI-PAY-001"}, {"id": "PI-PAY-002"}]}
        r = ca.audit(spec, "dummy.html")
        self.assertIn("C_PI_COVERAGE", self.invs(r))
        self.assertEqual(r["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
