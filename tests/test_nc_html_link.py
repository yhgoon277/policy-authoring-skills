"""nc_html_link 파서 자기검증 — data-속성 기반 PG→PI 변형.

주문계약 v0.45 full-document 골든 렌더는 MARKER('정책 항목 상세')·<hN id=PG> 가 없고
<a data-pi-id data-policy-id>이름 (PI-..)</a> 로만 PG 귀속을 명시한다. 기존 6변형·dev 폴백은
PG를 못 잡아 전부 PG-UNKNOWN 한 바구니로 담았다(R4 완료정합 오탐의 근인). 이 변형이 실 PG를
복원하는지 검증한다.
"""
import _toolpath  # noqa: F401
import unittest

import nc_html_link as nl

HTML_DATAATTR = """<html><body><h2>6. 정책 정의</h2>
<ul class="draft-list">
<li data-pi-id="PI-ORD-ENTRY-001-001"><a class="doc-link policy-item-link" data-pi-id="PI-ORD-ENTRY-001-001" data-policy-id="PG-ORD-ENTRY-001" href="#PI-ORD-ENTRY-001-001" data-parent-policy-id="PG-ORD-ENTRY-001">허용 진입 경로 기준 (PI-ORD-ENTRY-001-001)</a></li>
<li data-pi-id="PI-ORD-ENTRY-001-002"><a class="doc-link policy-item-link" data-pi-id="PI-ORD-ENTRY-001-002" data-policy-id="PG-ORD-ENTRY-001" href="#PI-ORD-ENTRY-001-002">진입값 필수성 기준 (PI-ORD-ENTRY-001-002)</a></li>
<li data-pi-id="PI-ORD-AUTH-001-001"><a class="doc-link policy-item-link" data-pi-id="PI-ORD-AUTH-001-001" data-policy-id="PG-ORD-AUTH-001" href="#PI-ORD-AUTH-001-001">본인인증 수준 기준 (PI-ORD-AUTH-001-001)</a></li>
</ul>
<p>교차참조: <a href="#PI-ORD-ENTRY-001-001" data-pi-id="PI-ORD-ENTRY-001-001">여기</a> 참고</p>
</body></html>"""


class DataAttrVariant(unittest.TestCase):
    def test_groups_pg_pi_by_data_attributes(self):
        m = nl.parse_pg_pi(HTML_DATAATTR)
        self.assertNotIn("PG-UNKNOWN", m, "data-policy-id로 실 PG 귀속되어야(PG-UNKNOWN 아님)")
        self.assertEqual(set(m), {"PG-ORD-ENTRY-001", "PG-ORD-AUTH-001"})
        self.assertEqual([x["id"] for x in m["PG-ORD-ENTRY-001"]],
                         ["PI-ORD-ENTRY-001-001", "PI-ORD-ENTRY-001-002"])
        self.assertEqual([x["id"] for x in m["PG-ORD-AUTH-001"]], ["PI-ORD-AUTH-001-001"])

    def test_extracts_name_without_piid_suffix(self):
        m = nl.parse_pg_pi(HTML_DATAATTR)
        self.assertEqual(m["PG-ORD-ENTRY-001"][0]["name"], "허용 진입 경로 기준")

    def test_crosslink_without_policy_id_not_double_counted(self):
        # data-policy-id 없는 교차참조 <a>는 PG 귀속 신호 아님 → 중복/오귀속 없이 총 3개 유지
        m = nl.parse_pg_pi(HTML_DATAATTR)
        self.assertEqual(sum(len(v) for v in m.values()), 3)


if __name__ == "__main__":
    unittest.main()
