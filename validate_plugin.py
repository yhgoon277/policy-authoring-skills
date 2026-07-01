#!/usr/bin/env python3
"""Plugin packaging validator — policy-authoring (Claude + Codex).

Pure stdlib. This is a *validator*, not a transformer: it never edits files,
it only asserts the cross-runtime packaging invariants that drift over time.

Checks:
  1. Every skills/<name>/ has SKILL.md AND agents/openai.yaml.
  2. Each SKILL.md frontmatter has name + description; name is [a-z0-9-] only
     and equals the directory name.
  3. Each agents/openai.yaml declares interface + allow_implicit_invocation.
  4. Claude (.claude-plugin/plugin.json) and Codex (.codex-plugin/plugin.json)
     version strings are present and equal. With --expect-version=X, both must equal X.
  5. The skill count is reported; with --expect-skills=N it must equal N.
  6. With --check-oracles: the 5-principle oracle tools exist AND the tests/ oracle
     self-test suite passes (python3 -m unittest discover -s tests). This makes the
     release loop gate on oracle health, not just packaging.

Exit 0 = all invariants hold; exit 1 = at least one violation (printed).

Usage:
  python3 validate_plugin.py [--expect-version=0.5.1] [--expect-skills=10] [--check-oracles] [--plugin=plugins/policy-authoring]
"""
import json
import os
import re
import subprocess
import sys

NAME_RE = re.compile(r"^[a-z0-9-]+$")

# 5원칙 오라클/파이프라인 도구(+SSOT 데이터·번들 게이트) — --check-oracles로 존재를 강제.
ORACLE_TOOLS = [
    "run_acceptance.py", "build_deliverable.py", "compare_fidelity.py", "completion_audit.py",
    "domain_code_map.py", "domain_code_normalize.py", "rebuild_policy_from_source.py",
    "fn_pi_derive.py", "source_html_index.py", "splice_nc_html.py", "render_preview.py",
    "validate_nc_input.py", "domain_codes.md",
]


def check_oracles(root, plugin):
    """오라클 도구 존재 + tests/ 자기검증 스위트 통과를 단언. 위반 목록 반환."""
    errs = []
    tools = os.path.join(plugin, "skills", "policy-authoring-setup", "assets", "tools")
    for t in ORACLE_TOOLS:
        if not os.path.isfile(os.path.join(tools, t)):
            errs.append(f"oracle tool missing: {t}")
    tests_dir = os.path.join(root, "tests")
    if not os.path.isdir(tests_dir):
        errs.append("tests/ 디렉터리 없음(오라클 자기검증 스위트)")
        return errs
    p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "tests"],
                       cwd=root, capture_output=True, text=True)
    out = (p.stderr or p.stdout or "").strip()
    if p.returncode != 0:
        tail = "\n    ".join(out.splitlines()[-15:])
        errs.append("oracle self-tests FAILED:\n    " + tail)
    else:
        print(f"oracles: {len(ORACLE_TOOLS)} tools present · self-tests {out.splitlines()[-1] if out else 'OK'}")
    return errs


def parse_frontmatter(path):
    """Return dict of top-level scalar frontmatter keys (name/description/version)."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end]
    fm = {}
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv):
    opts = {a.split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else "")
            for a in argv[1:] if a.startswith("--")}
    plugin_rel = opts.get("--plugin", "plugins/policy-authoring")
    expect_version = opts.get("--expect-version")
    expect_skills = opts.get("--expect-skills")

    root = os.path.dirname(os.path.abspath(__file__))
    plugin = os.path.join(root, plugin_rel)
    skills_dir = os.path.join(plugin, "skills")

    errors = []
    if not os.path.isdir(skills_dir):
        print(f"FAIL: skills dir not found: {skills_dir}")
        return 1

    skill_names = sorted(d for d in os.listdir(skills_dir)
                         if os.path.isdir(os.path.join(skills_dir, d)))

    for name in skill_names:
        d = os.path.join(skills_dir, name)
        skill_md = os.path.join(d, "SKILL.md")
        oai = os.path.join(d, "agents", "openai.yaml")

        if not os.path.isfile(skill_md):
            errors.append(f"{name}: missing SKILL.md")
        else:
            fm = parse_frontmatter(skill_md)
            if not fm:
                errors.append(f"{name}: SKILL.md has no parseable YAML frontmatter")
            else:
                if not fm.get("name"):
                    errors.append(f"{name}: frontmatter missing 'name'")
                elif not NAME_RE.match(fm["name"]):
                    errors.append(f"{name}: frontmatter name '{fm['name']}' has illegal chars (allow a-z0-9-)")
                elif fm["name"] != name:
                    errors.append(f"{name}: frontmatter name '{fm['name']}' != directory '{name}'")
                if not fm.get("description"):
                    errors.append(f"{name}: frontmatter missing 'description'")

        if not os.path.isfile(oai):
            errors.append(f"{name}: missing agents/openai.yaml")
        else:
            with open(oai, encoding="utf-8") as fh:
                y = fh.read()
            if "interface:" not in y:
                errors.append(f"{name}: openai.yaml missing 'interface:'")
            if "allow_implicit_invocation" not in y:
                errors.append(f"{name}: openai.yaml missing 'allow_implicit_invocation'")

    # Manifest version parity
    claude_mf = os.path.join(plugin, ".claude-plugin", "plugin.json")
    codex_mf = os.path.join(plugin, ".codex-plugin", "plugin.json")
    cv = xv = None
    try:
        cv = load_json(claude_mf).get("version")
    except Exception as e:
        errors.append(f"claude plugin.json unreadable: {e}")
    try:
        xv = load_json(codex_mf).get("version")
    except Exception as e:
        errors.append(f"codex plugin.json unreadable: {e}")
    if cv and xv and cv != xv:
        errors.append(f"version mismatch: claude={cv} codex={xv}")
    if expect_version:
        if cv != expect_version:
            errors.append(f"claude version {cv} != expected {expect_version}")
        if xv != expect_version:
            errors.append(f"codex version {xv} != expected {expect_version}")

    n = len(skill_names)
    if expect_skills and str(n) != str(expect_skills):
        errors.append(f"skill count {n} != expected {expect_skills}")

    if "--check-oracles" in opts:
        errors.extend(check_oracles(root, plugin))

    print(f"skills: {n} ({', '.join(skill_names)})")
    print(f"version: claude={cv} codex={xv}")
    if errors:
        print(f"\nFAIL — {len(errors)} violation(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nPASS — all packaging invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
