---
description: Render the 6-section preview HTML and produce the delivery HTML by splicing rich sections into the NC-converted base.
argument-hint: [unit-and-nc-base-html-context]
---

# Policy Render & Deliver

Use this command when the user wants to regenerate the preview HTML from the spec JSON and/or produce the final delivery HTML (the NC-converted document with rich policy-detail sections and styling spliced in).

## Arguments

The user invoked this command with: $ARGUMENTS

## Instructions

1. Read `skills/policy-authoring-setup/SKILL.md` (5단계·6단계 — render/splice) and, as needed, `skills/policy-authoring-setup/assets/schema/canonical_spec_schema.md`.
2. Run the project-local copied tools (installed from `assets/tools/`):
   ```bash
   python3 tools/render_preview.py --config=policy_config.json --unit=<unit>            # 6-section preview HTML
   python3 tools/splice_nc_html.py --config=policy_config.json --unit=<unit> --base=<NC 변환 HTML>
   ```
3. `render_preview.py` inlines `preview_style.css` and regenerates the 6-section preview (head/viewport/title/meta, inline table widths, usecase/state-transition mermaid diagrams). `splice_nc_html.py` replaces sections 5·6 of the NC-converted base with the preview's rich sections and idempotently injects rich CSS before `</body>` (non-replaced sections kept byte-for-byte).
4. Visually verify the preview and the spliced delivery HTML. The NC converter renders policy detail as flat text, so the splice step is required for a publish-quality deliverable.

## Example Usage

```text
/policy-render-deliver hub 유닛 미리보기·배포본 생성
/policy-authoring:policy-render-deliver NC 변환본 받아서 섹션 5·6 이식한 배포 HTML 만들어줘
```
