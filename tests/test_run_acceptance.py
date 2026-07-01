"""run_acceptance 자기검증 — 5원칙 3-상태 종합(DONE/BLOCKED/FAIL) 로직.

하위 오라클(compare_fidelity·completion_audit·source_html_index·_run_gate)은 monkeypatch로
격리하고, run_acceptance의 '종합 판정' 규칙만 검증한다. R2 게이트 기본 배선(번들)도 확인.
"""
import _toolpath  # noqa: F401
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import run_acceptance as ra

MEASURABLE = {"function_to_subfns": {"FN-PAY-001": ["a"]}, "pg_to_pis": {}}


class ThreeState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _spec(self, spec):
        p = os.path.join(self.tmp, "spec.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(spec, f)
        return p

    def _run(self, *, measurable=True, cf_findings=None, r4="PASS",
             gate=("PASS", 0, "errors=0"), spec=None):
        spec = spec or {"meta": {"business_code": "PAY"}, "functions": [{"id": "FN-PAY-001"}]}
        sp = self._spec(spec)
        oidx = MEASURABLE if measurable else {}
        with patch.object(ra.shi, "build_index", return_value=oidx), \
             patch.object(ra.cf, "compare", return_value={"findings": cf_findings or []}), \
             patch.object(ra.ca, "audit", return_value={"verdict": r4, "findings": []}), \
             patch.object(ra, "_run_gate", return_value=gate), \
             patch.object(ra.dcn, "check_r5",
                          return_value={"verdict": "PASS", "bad_ids": [], "business_code_ok": True}):
            return ra.run("src.html", sp, "deliv.html")

    def test_done(self):
        r = self._run()
        self.assertEqual(r["verdict"], "DONE")
        self.assertEqual(set(r["summary"].values()), {"PASS"})
        self.assertEqual(r["decisions"], [])

    def test_fail_on_r3_loss(self):
        r = self._run(cf_findings=[{"invariant": "FN_DROPPED", "severity": "HIGH",
                                    "principle": "R3", "key": "FN-PAY-002", "detail": "loss"}])
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["summary"]["R3"], "FAIL")

    def test_fail_on_r1_style(self):
        r = self._run(cf_findings=[{"invariant": "STYLE_POLICYLIST_PIID", "severity": "HIGH",
                                    "principle": "R1", "key": "policy_list", "detail": "no piid"}])
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["summary"]["R1"], "FAIL")

    def test_blocked_on_r2_gate_fail(self):
        r = self._run(gate=("FAIL", 3, "errors=3"))
        self.assertEqual(r["verdict"], "BLOCKED")
        self.assertEqual(r["summary"]["R2"], "FAIL")
        self.assertTrue(any(d["kind"] == "gate_authoring" for d in r["decisions"]))

    def test_r2_gate_runs_by_default(self):
        # 번들 게이트가 기본 실행되어 R2가 NA가 아니라 실측(PASS)됨
        r = self._run(gate=("PASS", 0, "errors=0"))
        self.assertEqual(r["summary"]["R2"], "PASS")

    def test_blocked_on_r5_unresolved(self):
        spec = {"functions": [{"id": "FN-ZZZ-001"}]}   # 미등록 세그 → target 미결
        r = self._run(spec=spec)
        self.assertEqual(r["verdict"], "BLOCKED")
        self.assertEqual(r["summary"]["R5"], "NA")
        self.assertTrue(any(d["kind"] == "target_unresolved" for d in r["decisions"]))

    def test_blocked_on_unsupported_format(self):
        r = self._run(measurable=False)
        self.assertEqual(r["verdict"], "BLOCKED")
        self.assertEqual(r["summary"]["R1"], "NA")
        self.assertTrue(any(d["kind"] == "unsupported_format" for d in r["decisions"]))

    def test_r1_med_is_decision_not_fail(self):
        # 완료게이트(FN_NO_POLICY, MED)는 FAIL이 아니라 사람결정(authoring_needed)
        r = self._run(cf_findings=[{"invariant": "FN_NO_POLICY", "severity": "MED",
                                    "principle": "R1", "key": "functions", "detail": "no policy"}])
        self.assertEqual(r["summary"]["R1"], "PASS")
        self.assertEqual(r["verdict"], "BLOCKED")
        self.assertTrue(any(d["kind"] == "authoring_needed" for d in r["decisions"]))


if __name__ == "__main__":
    unittest.main()
