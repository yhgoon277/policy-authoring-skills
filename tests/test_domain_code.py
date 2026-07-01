"""T-R5 오라클 자기검증 — 도메인코드 현행화(권위표 로드·resolve·relabel·check_r5·대화형 등록)."""
import _toolpath  # noqa: F401
import os
import shutil
import tempfile
import unittest

import domain_code_map as dcm
import domain_code_normalize as dcn


class TableLoad(unittest.TestCase):
    def test_md_is_ssot(self):
        auth, cur = dcm._load_table()
        self.assertGreaterEqual(len(auth), 30, "권위표 md에서 도메인이 로드되어야 함")
        self.assertIn("결제", auth)
        self.assertEqual(auth["결제"], "PAY")

    def test_fallback_when_missing(self):
        auth, cur = dcm._load_table("/nonexistent/domain_codes.md")
        self.assertTrue(auth, "md 부재 시 baked 폴백으로 무크래시")
        self.assertEqual(auth.get("결제"), "PAY")


class Resolve(unittest.TestCase):
    def test_current_alias(self):
        self.assertEqual(dcm.resolve_target("AIS"), "AIA")   # 브릿지 별칭
        self.assertEqual(dcm.resolve_target("MYI"), "INFO")
        self.assertEqual(dcm.resolve_target("ORD"), "JOIN")
        self.assertEqual(dcm.resolve_target("EVT"), "EVTMSN")

    def test_already_authoritative(self):
        # 이전 버그: 이미 현행화된 코드(INFO 등)가 미매핑→NA로 떨어졌음. 이제 그대로 인정.
        self.assertEqual(dcm.resolve_target("INFO"), "INFO")
        self.assertEqual(dcm.resolve_target("PAY"), "PAY")
        self.assertEqual(dcm.resolve_target("DTC"), "DTC")

    def test_unregistered(self):
        self.assertEqual(dcm.resolve_target("ZZZ"), "")      # 미등록 → 대화형 등록 유발

    def test_is_authoritative(self):
        self.assertTrue(dcm.is_authoritative("PAY"))
        self.assertTrue(dcm.is_authoritative("INFO"))
        self.assertFalse(dcm.is_authoritative("AIS"))        # 레거시 별칭은 권위코드 아님
        self.assertFalse(dcm.is_authoritative("ZZZ"))

    def test_code_for_name_strips_slash(self):
        self.assertEqual(dcm.code_for_name("이벤트/미션 프로그램"), "EVTMSN")
        self.assertEqual(dcm.code_for_name("결제"), "PAY")

    def test_suggest_code(self):
        self.assertEqual(dcm.suggest_code("AI Agent"), "AIAG")
        self.assertEqual(dcm.suggest_code("결제"), "")        # 한글 전용 → 사람이 확정


class CheckR5(unittest.TestCase):
    def test_pass(self):
        spec = {"meta": {"business_code": "PAY"},
                "functions": [{"id": "FN-PAY-001"}],
                "policy_groups": [{"id": "PG-PAY-001"}]}
        self.assertEqual(dcn.check_r5(spec, "PAY")["verdict"], "PASS")

    def test_fail_bad_seg(self):
        spec = {"meta": {"business_code": "PAY"},
                "functions": [{"id": "FN-OLD-001"}]}   # 세그 불일치
        r = dcn.check_r5(spec, "PAY")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("FN-OLD-001", r["bad_ids"])

    def test_local_id_excluded(self):
        # ACT-001 같은 모듈-로컬 번호 스킴은 도메인코드 대상 밖
        spec = {"meta": {"business_code": "PAY"}, "actors": [{"id": "ACT-001"}],
                "functions": [{"id": "FN-PAY-001"}]}
        self.assertEqual(dcn.check_r5(spec, "PAY")["verdict"], "PASS")

    def test_normalize_relabels(self):
        spec = {"functions": [{"id": "FN-OLD-001", "related_functions": ["FN-OLD-002"]}]}
        out = dcn.normalize_spec_to(spec, "PAY")
        self.assertEqual(out["functions"][0]["id"], "FN-PAY-001")
        self.assertEqual(out["functions"][0]["related_functions"], ["FN-PAY-002"])
        self.assertEqual(out["meta"]["business_code"], "PAY")
        # 관계구조 보존(라벨만 변경): 원본 미변형
        self.assertEqual(spec["functions"][0]["id"], "FN-OLD-001")


class AddDomain(unittest.TestCase):
    """대화형 등록: 미등록 도메인을 md에 추가하면 즉시 인식."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.md = os.path.join(self.tmp, "domain_codes.md")
        shutil.copy(dcm.table_path(), self.md)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        # 모듈 전역을 실제 md로 복원(같은 프로세스의 다른 테스트 보호)
        dcm.AUTHORITATIVE, dcm.CURRENT_CODE_TO_NAME = dcm._load_table()

    def test_round_trip(self):
        code = dcm.add_domain("가상 신규 도메인", "NEWD", alias="NEW", note="테스트", path=self.md)
        self.assertEqual(code, "NEWD")
        auth, cur = dcm._load_table(self.md)
        self.assertEqual(auth["가상 신규 도메인"], "NEWD")
        self.assertEqual(cur["NEW"], "가상 신규 도메인")
        # 모듈 전역도 갱신되어 resolve가 즉시 인식
        self.assertEqual(dcm.resolve_target("NEW"), "NEWD")

    def test_idempotent(self):
        dcm.add_domain("가상 신규 도메인", "NEWD", path=self.md)
        again = dcm.add_domain("가상 신규 도메인", "OTHER", path=self.md)
        self.assertEqual(again, "NEWD", "기존 도메인은 재등록하지 않고 기존 코드 반환")
        auth, _ = dcm._load_table(self.md)
        self.assertEqual(auth["가상 신규 도메인"], "NEWD")


if __name__ == "__main__":
    unittest.main()
