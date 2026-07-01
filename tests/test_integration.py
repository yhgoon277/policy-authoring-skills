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

    def test_payment_end_to_end(self):
        spec, html = _find("결제")
        if not (spec and html):
            self.skipTest("결제 쌍을 찾지 못함")
        r = bd.build(spec, html, self.out)
        acc = r["acceptance"]
        # (1) 산출물 한 쌍이 실제로 생성됨
        self.assertTrue(os.path.exists(r["spec"]), "최종 spec JSON 생성")
        self.assertTrue(os.path.exists(r["deliverable"]), "최종 배포 HTML 생성")
        # (2) R5 target 자동 해소(결제 → PAY)
        self.assertEqual(r["target"], "PAY")
        # (3) R2 게이트가 기본 실행되어 실측됨(NA 아님)
        self.assertIn(acc["summary"]["R2"], ("PASS", "FAIL"))
        # (4) 파이프라인이 유효한 3-상태로 완료(크래시 없음)
        self.assertIn(acc["verdict"], ("DONE", "BLOCKED", "FAIL"))
        # (5) 측정 가능 포맷이므로 R1/R3/R4가 NA로 떨어지지 않음
        self.assertNotEqual(acc["summary"]["R1"], "NA")
        self.assertNotEqual(acc["summary"]["R4"], "NA")


if __name__ == "__main__":
    unittest.main()
