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


class PreserveMode(Base):
    def test_identical_after_relabel_passes(self):
        i = idx(f2s={"FN-EVTMSN-CUS-001": ["a"]}, f2pi={"FN-EVTMSN-CUS-001": ["PI-EVTMSN-X-001-01"]})
        o = self.mk("o.html", "<h2>5.</h2> FN-EVT-CUS-001", i)
        g = self.mk("g.html", "<h2>5.</h2> FN-EVTMSN-CUS-001", i)
        r = cf.compare(o, g, target_code="EVTMSN", mode="preserve")
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(r["findings"], [])

    def test_full_document_diff_fails_as_r3(self):
        i = idx()
        o = self.mk("o.html", "<h2>5.</h2> body", i)
        g = self.mk("g.html", "<h2>5.</h2> DIFFERENT", i)
        r = cf.compare(o, g, mode="preserve")
        self.assertIn("FULL_PRESERVED", self.invs(r))
        self.assertEqual(self.principle_of(r, "FULL_PRESERVED"), "R3")
        self.assertEqual(r["verdict"], "FAIL")

    def test_preserve_skips_golden_style_checks(self):
        txt = '<h2>5.</h2><table class="policy-list-table">no-id</table>'
        i = idx(f2s={"FN-EVTMSN-CUS-001": ["a"]})   # 관련 PI 없음 → golden이면 FN_NO_POLICY
        o = self.mk("o.html", txt, i)
        g = self.mk("g.html", txt, i)
        r = cf.compare(o, g, mode="preserve")
        self.assertEqual(r["findings"], [])                      # 스타일·완료게이트 미적용
        r2 = cf.compare(o, g, mode="golden")
        self.assertIn("STYLE_POLICYLIST_PIID", self.invs(r2))    # golden은 기존 그대로


def idx2(base=None, pg_list=None, pg_detail=None):
    d = base or idx()
    d["pg_list_names"] = pg_list or {}
    d["pg_detail_names"] = pg_detail or {}
    return d


class PgListDetailMismatch(Base):
    def test_mismatch_reported_once_as_med_r3(self):
        i = idx2(pg_list={"PG-EVT-A-001": ["가", "나"], "PG-EVT-B-001": ["다"]},
                 pg_detail={"PG-EVT-A-001": ["가"], "PG-EVT-B-001": ["다"]})
        o = self.mk("o.html", "<h2>5.</h2>x", i)
        g = self.mk("g.html", "<h2>5.</h2>x", i)
        r = cf.compare(o, g)
        f = [x for x in r["findings"] if x["invariant"] == "PG_LIST_DETAIL_MISMATCH"]
        self.assertEqual(len(f), 1)                      # PG별이 아니라 단일 집계
        self.assertEqual(f[0]["severity"], "MED")
        self.assertEqual(f[0]["principle"], "R3")
        self.assertIn("PG-EVT-A-001", f[0]["detail"])
        self.assertEqual(r["verdict"], "PASS")           # MED는 FAIL 아님

    def test_match_silent(self):
        i = idx2(pg_list={"PG-EVT-A-001": ["가", "나"]}, pg_detail={"PG-EVT-A-001": ["나", "가"]})
        o = self.mk("o.html", "x", i)
        g = self.mk("g.html", "x", i)
        r = cf.compare(o, g)
        self.assertNotIn("PG_LIST_DETAIL_MISMATCH", self.invs(r))

    def test_empty_detail_names_not_compared(self):
        # 이름 추출 실패(빈 집합)는 비교 불능 — 가짝 불일치 금지
        i = idx2(pg_list={"PG-EVT-A-001": ["가", "나"]}, pg_detail={"PG-EVT-A-001": []})
        o = self.mk("o.html", "x", i)
        g = self.mk("g.html", "x", i)
        r = cf.compare(o, g)
        self.assertNotIn("PG_LIST_DETAIL_MISMATCH", self.invs(r))


class PgListDetailDecorations(Base):
    """F5: 렌더 장식(목록 ID 접미·상세 검토 배지)만 다른 동일 구성을 불일치로 오탐했던 버그."""

    def test_id_suffix_and_field_review_badge_stripped(self):
        i = idx2(pg_list={"PG-EVT-A-001": ["접근 허용 범위 (PI-EVT-A-001-01)",
                                           "권한 제한 대상 (PI-EVT-A-001-02)"]},
                 pg_detail={"PG-EVT-A-001": ["접근 허용 범위",
                                             "권한 제한 대상 BSS/현업 검토 필요"]})
        o = self.mk("o.html", "x", i)
        g = self.mk("g.html", "x", i)
        r = cf.compare(o, g)
        self.assertNotIn("PG_LIST_DETAIL_MISMATCH", self.invs(r))

    def test_internal_integration_badge_stripped(self):
        i = idx2(pg_list={"PG-EVT-A-001": ["다채널 게시 (PI-EVT-A-001-03)"]},
                 pg_detail={"PG-EVT-A-001": ["다채널 게시 내부 통합 필요"]})
        o = self.mk("o.html", "x", i)
        g = self.mk("g.html", "x", i)
        r = cf.compare(o, g)
        self.assertNotIn("PG_LIST_DETAIL_MISMATCH", self.invs(r))

    def test_real_mismatch_still_detected(self):
        # 장식 제거 후에도 실제 구성 차이(PI 누락)는 계속 검출 — 검출력 보존 가드
        i = idx2(pg_list={"PG-EVT-A-001": ["가 (PI-EVT-A-001-01)", "나 (PI-EVT-A-001-02)"]},
                 pg_detail={"PG-EVT-A-001": ["가"]})
        o = self.mk("o.html", "x", i)
        g = self.mk("g.html", "x", i)
        r = cf.compare(o, g)
        f = [x for x in r["findings"] if x["invariant"] == "PG_LIST_DETAIL_MISMATCH"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "MED")


if __name__ == "__main__":
    unittest.main()
