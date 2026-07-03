"""통합 자기검증 — 실 NC 정책서 1쌍을 build_deliverable로 end-to-end 실행.

파서(source_html_index)·파이프라인·번들 R2 게이트·R5 해소를 실데이터로 관통 검증한다.
입력 테스트셋이 없는 머신(팀원 등)에서는 skip — 회귀 스위트가 데이터 의존으로 깨지지 않게.
"""
import _toolpath  # noqa: F401
import os
import shutil
import tempfile
import unicodedata
import unittest

from _toolpath import INPUT_DIR

import build_deliverable as bd

HAVE_DATA = os.path.isdir(INPUT_DIR)


def _find(keyword):
    """macOS 파일명은 NFD로 저장 → NFC 정규화 후 부분일치(glob NFC 패턴은 매칭 실패)."""
    kw = unicodedata.normalize("NFC", keyword)
    spec = html = None
    for fn in sorted(os.listdir(INPUT_DIR)) if HAVE_DATA else []:
        n = unicodedata.normalize("NFC", fn)
        if kw not in n:
            continue
        full = os.path.join(INPUT_DIR, fn)
        if n.endswith("_spec.json") and spec is None:
            spec = full
        elif n.endswith(".html") and html is None:
            html = full
    return spec, html


@unittest.skipUnless(HAVE_DATA, f"입력 테스트셋 없음: {INPUT_DIR}")
class BuildDeliverable(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def test_payment_end_to_end_golden_default(self):
        spec, html = _find("결제")
        if not (spec and html):
            self.skipTest("결제 쌍을 찾지 못함")
        r = bd.build(spec, html, self.out)
        acc = r["acceptance"]
        self.assertTrue(os.path.exists(r["spec"]) and os.path.exists(r["deliverable"]))
        self.assertEqual(r["target"], "PAY")
        self.assertIn(acc["summary"]["R2"], ("PASS", "FAIL"))
        self.assertIn(acc["verdict"], ("DONE", "BLOCKED", "FAIL"))
        # 골든 기본: R1은 측정된다(WAIVED/NA 아님)
        self.assertIn(acc["summary"]["R1"], ("PASS", "FAIL"))
        self.assertNotEqual(acc["summary"]["R4"], "NA")

    def test_payment_end_to_end_preserve_optin(self):
        spec, html = _find("결제")
        if not (spec and html):
            self.skipTest("결제 쌍을 찾지 못함")
        r = bd.build(spec, html, self.out, preserve=True)
        acc = r["acceptance"]
        # 보존 옵트인: R1=WAIVED 명시 + 배포물 = relabel(원천) byte-동일(줄끝 포함)
        self.assertEqual(acc["summary"]["R1"], "WAIVED")
        import domain_code_normalize as dcn
        with open(html, encoding="utf-8", newline="") as f:
            src_txt = f.read()
        with open(r["deliverable"], encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), dcn.relabel_to(src_txt, r["target"]))


if __name__ == "__main__":
    unittest.main()
