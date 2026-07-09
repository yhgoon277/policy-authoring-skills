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
        self.assertEqual(auth["주문/계약/가입"], "ORD")  # 2026-07 현행화: 권위=ORD

    def test_fallback_when_missing(self):
        auth, cur = dcm._load_table("/nonexistent/domain_codes.md")
        self.assertTrue(auth, "md 부재 시 baked 폴백으로 무크래시")
        self.assertEqual(auth.get("결제"), "PAY")

    def test_baked_mirrors_md(self):
        # 가드: baked 폴백은 SSOT(md)의 미러 — 표만 고치고 폴백을 빠뜨리는 실수를 차단
        self.assertTrue(os.path.exists(dcm.table_path()), "SSOT md 부재 시 폴백끼리 자기비교로 무의미 통과 방지")
        auth, cur = dcm._load_table()
        self.assertEqual(auth, dcm._BAKED_AUTHORITATIVE)
        self.assertEqual(cur, dcm._BAKED_CURRENT)


class Resolve(unittest.TestCase):
    def test_current_alias(self):
        self.assertEqual(dcm.resolve_target("AIS"), "AIA")   # 브릿지 별칭
        self.assertEqual(dcm.resolve_target("MYI"), "INFO")
        self.assertEqual(dcm.resolve_target("JOIN"), "ORD")  # 구권위 JOIN → 현행 ORD
        self.assertEqual(dcm.resolve_target("EVT"), "EVTMSN")

    def test_already_authoritative(self):
        # 이전 버그: 이미 현행화된 코드(INFO 등)가 미매핑→NA로 떨어졌음. 이제 그대로 인정.
        self.assertEqual(dcm.resolve_target("INFO"), "INFO")
        self.assertEqual(dcm.resolve_target("PAY"), "PAY")
        self.assertEqual(dcm.resolve_target("DTC"), "DTC")
        self.assertEqual(dcm.resolve_target("ORD"), "ORD")   # 2026-07 현행화로 ORD가 권위

    def test_unregistered(self):
        self.assertEqual(dcm.resolve_target("ZZZ"), "")      # 미등록 → 대화형 등록 유발

    def test_is_authoritative(self):
        self.assertTrue(dcm.is_authoritative("PAY"))
        self.assertTrue(dcm.is_authoritative("INFO"))
        self.assertTrue(dcm.is_authoritative("ORD"))         # 2026-07 현행화로 권위
        self.assertFalse(dcm.is_authoritative("AIS"))        # 레거시 별칭은 권위코드 아님
        self.assertFalse(dcm.is_authoritative("JOIN"))       # 구권위 → 이제 alias
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


class ActorPrefixRelabel(unittest.TestCase):
    """F2: AC- 액터 접두가 _PREFIX에 없어 relabel_to는 건너뛰고 check_r5는 무는 비정합."""

    def test_ac_prefix_relabels(self):
        self.assertEqual(dcn.relabel_to("AC-CS-01", "CSHUB"), "AC-CSHUB-01")

    def test_module_local_ac_untouched(self):
        # 2토막 모듈-로컬 스킴은 도메인코드 비대상 — 기존 ACT-001 규칙과 동일
        self.assertEqual(dcn.relabel_to("AC-001", "CSHUB"), "AC-001")
        self.assertEqual(dcn.relabel_to("ACT-001", "CSHUB"), "ACT-001")

    def test_word_boundary_no_false_match(self):
        self.assertEqual(dcn.relabel_to("MAC-CS-01", "CSHUB"), "MAC-CS-01")

    def test_normalize_then_check_r5_consistent(self):
        spec = {"meta": {"business_code": "CS"},
                "actors": [{"id": "AC-CS-01"}, {"id": "AC-CS-02"}],
                "usecases": [{"id": "UC-CS-CS-01"}]}
        out = dcn.normalize_spec_to(spec, "CSHUB")
        self.assertEqual([a["id"] for a in out["actors"]], ["AC-CSHUB-01", "AC-CSHUB-02"])
        r5 = dcn.check_r5(out, "CSHUB")
        self.assertEqual(r5["verdict"], "PASS", r5["bad_ids"])


class DictKeyRelabel(unittest.TestCase):
    """F4: _walk가 dict 값만 relabel하고 키를 건너뛰어 trace_matrix 키(구코드)↔값(신코드) 오염."""

    def test_trace_matrix_keys_relabelled(self):
        spec = {"meta": {"business_code": "CS"},
                "trace_matrix": {
                    "uc_to_process": {"UC-CS-CS-01": ["PR-CS-HUB-001"]},
                    "policy_detail_to_function": {"PI-CS-ACC-01-01": ["FN-CS-HUB-001"]}}}
        out = dcn.normalize_spec_to(spec, "CSHUB")
        tm = out["trace_matrix"]
        self.assertEqual(tm["uc_to_process"], {"UC-CSHUB-CS-01": ["PR-CSHUB-HUB-001"]})
        self.assertEqual(tm["policy_detail_to_function"], {"PI-CSHUB-ACC-01-01": ["FN-CSHUB-HUB-001"]})

    def test_plain_keys_untouched(self):
        out = dcn.normalize_spec_to(
            {"process_details": {"평문 키": {"UC-CS-CS-01": "값 PR-CS-HUB-001"}}}, "CSHUB")
        self.assertEqual(out["process_details"],
                         {"평문 키": {"UC-CSHUB-CS-01": "값 PR-CSHUB-HUB-001"}})


class FcAndTwoPartRelabel(unittest.TestCase):
    """FC 접두 + 2토막 문서ID(POL-MYI) relabel, 숫자세그는 불변."""

    def test_fc_prefix_relabels(self):
        self.assertEqual(dcn.relabel_to("FC-MYI-QA-CASE", "INFO"), "FC-INFO-QA-CASE")

    def test_two_part_document_id_relabels(self):
        self.assertEqual(dcn.relabel_to("POL-MYI", "INFO"), "POL-INFO")

    def test_functional_two_part_preserved(self):
        # 기능형 2토막 ID(2번째 토큰이 도메인코드 아님)는 relabel 안 함 — 손상/충돌 방지.
        self.assertEqual(dcn.relabel_to("PG-AMOUNT", "BIL"), "PG-AMOUNT")
        self.assertEqual(dcn.relabel_to("PG-ALERT", "BIL"), "PG-ALERT")
        self.assertEqual(dcn.relabel_to("PG-OLD", "PAY"), "PG-OLD")

    def test_relationship_token_preserved(self):
        # 2번째 토큰이 엔티티 접두(PG-PI-FN의 'PI')면 도메인코드가 아님 — relabel 대상 아님.
        # 자유서술 'PG-PI-FN crosslink'가 'PG-ORD-FN'으로 조용히 손상되는 것을 막는다.
        self.assertEqual(dcn.relabel_to("PG-PI-FN crosslink", "ORD"), "PG-PI-FN crosslink")
        # 진짜 도메인세그(OLD)는 여전히 relabel
        self.assertEqual(dcn.relabel_to("FN-OLD-001-01", "ORD"), "FN-ORD-001-01")

    def test_numeric_seg_untouched(self):
        self.assertEqual(dcn.relabel_to("ACT-001", "INFO"), "ACT-001")
        self.assertEqual(dcn.relabel_to("PM-20", "INFO"), "PM-20")

    def test_existing_three_part_still_relabels(self):
        self.assertEqual(dcn.relabel_to("FN-OLD-001", "PAY"), "FN-PAY-001")
        self.assertEqual(dcn.relabel_to("AC-CS-01", "CSHUB"), "AC-CSHUB-01")


class CheckR5Comprehensive(unittest.TestCase):
    """전수 재귀: document_id·final_check·trace_matrix 등 전 필드 검출."""

    def test_document_id_flagged(self):
        spec = {"meta": {"business_code": "INFO", "document_id": "POL-MYI"},
                "functions": [{"id": "FN-INFO-001"}]}
        r = dcn.check_r5(spec, "INFO")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("POL-MYI", r["bad_ids"])

    def test_final_check_flagged(self):
        spec = {"meta": {"business_code": "INFO"},
                "final_check": [{"id": "FC-MYI-QA-CASE"}]}
        self.assertIn("FC-MYI-QA-CASE", dcn.check_r5(spec, "INFO")["bad_ids"])

    def test_trace_matrix_value_flagged(self):
        spec = {"meta": {"business_code": "INFO"},
                "trace_matrix": [{"item_id": "PI-MYI-SUM-001-01"}]}
        self.assertIn("PI-MYI-SUM-001-01", dcn.check_r5(spec, "INFO")["bad_ids"])

    def test_clean_spec_passes(self):
        spec = {"meta": {"business_code": "INFO", "document_id": "POL-INFO"},
                "final_check": [{"id": "FC-INFO-QA-CASE"}],
                "functions": [{"id": "FN-INFO-001"}],
                "actors": [{"id": "ACT-001"}]}
        self.assertEqual(dcn.check_r5(spec, "INFO")["verdict"], "PASS")

    def test_scan_returns_id_and_seg(self):
        got = dcn.scan_residual_segs({"a": "POL-MYI", "b": ["FC-MYI-QA-X"]}, "INFO")
        self.assertEqual({d["id"] for d in got}, {"POL-MYI", "FC-MYI-QA-X"})
        self.assertEqual({d["seg"] for d in got}, {"MYI"})

    def test_trace_matrix_idkey_flagged(self):
        # trace_matrix가 ID-키 맵일 때 키(구코드)도 검출, 값(현행코드)은 미검출
        spec = {"meta": {"business_code": "INFO"},
                "trace_matrix": {"UC-MYI-CS-01": ["FN-INFO-001"]}}
        r = dcn.check_r5(spec, "INFO")
        self.assertIn("UC-MYI-CS-01", r["bad_ids"])
        self.assertNotIn("FN-INFO-001", r["bad_ids"])

    def test_functional_two_part_not_flagged(self):
        # 기능형 2토막 PG(PG-AMOUNT 등)는 잔존코드가 아니므로 R5 FAIL 유발 안 함
        spec = {"meta": {"business_code": "BIL"},
                "policy_groups": [{"id": "PG-AMOUNT"}, {"id": "PG-ALERT"}]}
        self.assertEqual(dcn.check_r5(spec, "BIL")["verdict"], "PASS")

    def test_prose_relationship_token_not_flagged(self):
        # ID 모양이나 2번째 토큰이 엔티티 접두(PG-PI-FN의 'PI')인 관계 서술 토큰은 잔존
        # 도메인코드가 아님 — 도메인코드는 엔티티 접두(UC/PR/FN/PG/PI…)와 겹치지 않으므로,
        # 자유서술 meta(structure_enrichment.purpose 등)의 'PG-PI-FN crosslink' 오탐을 차단.
        spec = {"meta": {"business_code": "ORD",
                         "structure_enrichment": {
                             "purpose": "HTML policy detail structure and PG-PI-FN crosslink enrichment."}},
                "policy_groups": [{"id": "PG-ORD-ENTRY-001"}]}
        r = dcn.check_r5(spec, "ORD")
        self.assertEqual(r["verdict"], "PASS", r["bad_ids"])
        self.assertNotIn("PG-PI-FN", r["bad_ids"])

    def test_real_residual_still_flagged_near_entity_prefix(self):
        # 가드: 엔티티 접두 스킵이 진짜 잔존코드까지 놓치면 안 됨. seg가 도메인코드(OLD)면 검출 유지.
        spec = {"meta": {"business_code": "ORD"}, "functions": [{"id": "FN-OLD-001-01"}]}
        r = dcn.check_r5(spec, "ORD")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("FN-OLD-001-01", r["bad_ids"])

    def test_three_token_pol_id_not_corrupted(self):
        # POL-<code>-<rest>(정책상세 대체 ID)는 _ID_SEG로만 처리,
        # _DOCID_RE가 백트래킹으로 손상(POL-INF→POL-INFOO 등) / 오탐시키지 않음
        self.assertEqual(dcn.relabel_to("POL-MBR-TERM-001-01", "PAY"), "POL-PAY-TERM-001-01")
        self.assertEqual(dcn.scan_residual_segs("POL-PAY-TERM-001-01", "PAY"), [])
        # 2토막 문서ID는 여전히 처리
        self.assertEqual(dcn.relabel_to("POL-MYI", "INFO"), "POL-INFO")


class CheckR5Html(unittest.TestCase):
    """배포 HTML의 잔존 도메인코드(문서ID POL-MYI 등) 검출."""

    def test_html_residual_flagged(self):
        html = '<table><tr><td>정책서 ID</td><td>POL-MYI</td></tr></table>'
        r = dcn.check_r5_html(html, "INFO")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("POL-MYI", r["bad_ids"])

    def test_html_current_codes_pass(self):
        html = '<td>POL-INFO</td><td>FN-INFO-CUS-001</td>'
        self.assertEqual(dcn.check_r5_html(html, "INFO")["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
