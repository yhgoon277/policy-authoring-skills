"""T-R1/R3 오라클 자기검증 — 충실성(원천 손실·무단 발산·헤드 완전보존·골든 스타일).

build_index(파서)는 monkeypatch로 격리하고 오라클의 판정 로직만 검증한다(파서 자체는
test_integration에서 실데이터로 커버). 헤드/스타일 텍스트 검사는 실제 소형 HTML 파일로 구동.
"""
import _toolpath  # noqa: F401
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import compare_fidelity as cf


def idx(f2s=None, p2f=None, pg2pi=None, f2pi=None):
    return {"process_to_functions": p2f or {}, "process_to_policy_groups": {},
            "function_to_subfns": f2s or {}, "function_to_pis": f2pi or {},
            "pg_to_pis": pg2pi or {}, "function_names": {}, "function_descriptions": {}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.reg = {}
        self.patcher = patch.object(cf.shi, "build_index", side_effect=lambda p: self.reg[p])
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mk(self, name, text, index):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.reg[path] = index
        return path

    @staticmethod
    def invs(r):
        return {f["invariant"] for f in r["findings"]}

    @staticmethod
    def principle_of(r, inv):
        return next(f["principle"] for f in r["findings"] if f["invariant"] == inv)


class Clean(Base):
    def test_pass(self):
        ix = idx(f2s={"FN-PAY-001": ["a"]}, p2f={"PR-PAY-001": ["FN-PAY-001"]},
                 pg2pi={"PG-PAY-001": ["PI-PAY-001"]}, f2pi={"FN-PAY-001": ["PI-PAY-001"]})
        o = self.mk("o.html", "<html>x</html>", ix)
        g = self.mk("g.html", "<html>x</html>", dict(ix))
        r = cf.compare(o, g)
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(r["summary"]["high"], 0)


class Loss(Base):
    def test_fn_dropped_is_r3_high(self):
        o = self.mk("o.html", "<html>x</html>",
                    idx(f2s={"FN-PAY-001": ["a"], "FN-PAY-002": ["b"]},
                        p2f={"PR-PAY-001": ["FN-PAY-001", "FN-PAY-002"]}))
        g = self.mk("g.html", "<html>x</html>",
                    idx(f2s={"FN-PAY-001": ["a"]},
                        p2f={"PR-PAY-001": ["FN-PAY-001", "FN-PAY-002"]},
                        f2pi={"FN-PAY-001": ["PI-PAY-001"]}))
        r = cf.compare(o, g)
        self.assertIn("FN_DROPPED", self.invs(r))
        self.assertEqual(self.principle_of(r, "FN_DROPPED"), "R3")
        self.assertEqual(r["verdict"], "FAIL")

    def test_pi_lost(self):
        o = self.mk("o.html", "<html>x</html>",
                    idx(pg2pi={"PG-PAY-001": ["PI-PAY-001", "PI-PAY-002"]}))
        g = self.mk("g.html", "<html>x</html>",
                    idx(pg2pi={"PG-PAY-001": ["PI-PAY-001"]}))
        r = cf.compare(o, g)
        self.assertIn("PI_LOST", self.invs(r))
        self.assertEqual(r["verdict"], "FAIL")


class Divergence(Base):
    def _pair(self):
        # gen도 동일 p2f를 가져 PR_FN_LOST가 새지 않게 → FN_ADDED(발산)만 격리 검증.
        p2f = {"PR-PAY-001": ["FN-PAY-001"]}
        o = self.mk("o.html", "<html>x</html>",
                    idx(f2s={"FN-PAY-001": ["a"]}, p2f=p2f,
                        f2pi={"FN-PAY-001": ["PI-PAY-001"]}))
        g = self.mk("g.html", "<html>x</html>",
                    idx(f2s={"FN-PAY-001": ["a"], "FN-PAY-999": ["z"]}, p2f=dict(p2f),
                        f2pi={"FN-PAY-001": ["PI-PAY-001"], "FN-PAY-999": ["PI-PAY-009"]}))
        return o, g

    def test_fn_added_is_r3_high(self):
        o, g = self._pair()
        r = cf.compare(o, g)
        self.assertIn("FN_ADDED", self.invs(r))
        self.assertEqual(self.principle_of(r, "FN_ADDED"), "R3")
        self.assertEqual(r["verdict"], "FAIL")

    def test_approved_exempts_divergence(self):
        o, g = self._pair()
        r = cf.compare(o, g, approved=["FN-PAY-999"])
        self.assertNotIn("FN_ADDED", self.invs(r))
        self.assertEqual(r["verdict"], "PASS")


class HeadPreserved(Base):
    def test_head_change_flags_r3(self):
        ix = idx(f2s={"FN-PAY-001": ["a"]}, f2pi={"FN-PAY-001": ["PI-PAY-001"]})
        o = self.mk("o.html", "<h2>0. 히스토리</h2>AAA<h2>5. 기능</h2>BODY", ix)
        g = self.mk("g.html", "<h2>0. 히스토리</h2>BBB<h2>5. 기능</h2>BODY", dict(ix))
        r = cf.compare(o, g)
        self.assertIn("HEAD_PRESERVED", self.invs(r))
        self.assertEqual(self.principle_of(r, "HEAD_PRESERVED"), "R3")

    def test_identical_head_ok(self):
        ix = idx(f2s={"FN-PAY-001": ["a"]}, f2pi={"FN-PAY-001": ["PI-PAY-001"]})
        head = "<h2>0. 히스토리</h2>SAME<h2>5. 기능</h2>BODY"
        o = self.mk("o.html", head, ix)
        g = self.mk("g.html", head, dict(ix))
        r = cf.compare(o, g)
        self.assertNotIn("HEAD_PRESERVED", self.invs(r))


class GoldenStyle(Base):
    def test_policylist_missing_piid_is_r1(self):
        ix = idx(f2s={"FN-PAY-001": ["a"]}, f2pi={"FN-PAY-001": ["PI-PAY-001"]})
        o = self.mk("o.html", "<html>x</html>", ix)
        g = self.mk("g.html", '<h2>5. 기능</h2><table class="policy-list-table"><tr><td>정책명</td></tr></table>',
                    dict(ix))
        r = cf.compare(o, g)
        self.assertIn("STYLE_POLICYLIST_PIID", self.invs(r))
        self.assertEqual(self.principle_of(r, "STYLE_POLICYLIST_PIID"), "R1")

    def test_policylist_with_piid_ok(self):
        ix = idx(f2s={"FN-PAY-001": ["a"]}, f2pi={"FN-PAY-001": ["PI-PAY-001"]})
        o = self.mk("o.html", "<html>x</html>", ix)
        g = self.mk("g.html", '<h2>5. 기능</h2><table class="policy-list-table"><tr><td>정책명 (PI-PAY-001)</td></tr></table>',
                    dict(ix))
        r = cf.compare(o, g)
        self.assertNotIn("STYLE_POLICYLIST_PIID", self.invs(r))

    def test_fn_without_policy_is_med_completion_gate(self):
        ix_o = idx(f2s={"FN-PAY-001": ["a"]})
        ix_g = idx(f2s={"FN-PAY-001": ["a"]}, f2pi={})   # 관련 정책상세 없음
        o = self.mk("o.html", "<html>x</html>", ix_o)
        g = self.mk("g.html", "<html>x</html>", ix_g)
        r = cf.compare(o, g)
        self.assertIn("FN_NO_POLICY", self.invs(r))
        sev = next(f["severity"] for f in r["findings"] if f["invariant"] == "FN_NO_POLICY")
        self.assertEqual(sev, "MED")


if __name__ == "__main__":
    unittest.main()
