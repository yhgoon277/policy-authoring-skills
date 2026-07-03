"""build_deliverable 자기검증 — 보존 기본(배포물=relabel(원천)) · --golden 옵트인 splice 경로."""
import _toolpath  # noqa: F401
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import build_deliverable as bd
import domain_code_normalize as dcn

SRC = "<h2>5. 기능 정의</h2> FN-EVT-CUS-001 <h2>6. 정책 정의</h2> PG-EVT-PROG-001"
SPEC = {"meta": {}, "functions": [{"id": "FN-EVTMSN-CUS-001"}]}


def _fake_preview(spec, out):
    with open(out, "w", encoding="utf-8") as f:
        f.write("<preview/>")


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src.html")
        with open(self.src, "w", encoding="utf-8") as f:
            f.write(SRC)
        self.spec = os.path.join(self.tmp, "spec.json")
        with open(self.spec, "w", encoding="utf-8") as f:
            json.dump(SPEC, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _build(self, **kw):
        with patch.object(bd.rb, "rebuild", side_effect=lambda s, *a, **k: s), \
             patch.object(bd.fpd, "derive_fn_pi", side_effect=lambda s: (s, [])), \
             patch.object(bd, "_render_preview", side_effect=_fake_preview), \
             patch.object(bd.S, "extract_rich_css", return_value=""), \
             patch.object(bd.S, "inject_css", side_effect=lambda b, c: (b, 0)), \
             patch.object(bd.S, "splice_sections", return_value="<golden/>") as spl, \
             patch.object(bd.ra, "run",
                          return_value={"verdict": "DONE", "summary": {}, "decisions": []}) as rar:
            r = bd.build(self.spec, self.src, self.tmp, target_code="EVTMSN", **kw)
        return r, spl, rar

    def test_golden_default_splices(self):
        r, spl, rar = self._build()
        with open(r["deliverable"], encoding="utf-8") as f:
            self.assertEqual(f.read(), "<golden/>")
        spl.assert_called_once()
        self.assertEqual(rar.call_args.kwargs.get("mode"), "golden")

    def test_preserve_optin_is_relabeled_source(self):
        r, spl, rar = self._build(preserve=True)
        with open(r["deliverable"], encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), dcn.relabel_to(SRC, "EVTMSN"))
        spl.assert_not_called()
        self.assertEqual(rar.call_args.kwargs.get("mode"), "preserve")


if __name__ == "__main__":
    unittest.main()
