#!/usr/bin/env bash
# Rebuild dist/ ZIPs reproducibly:
#   - <skill>.zip       : one per skill, folder contents MINUS agents/ (Codex-only) — for claude.ai/Desktop upload
#   - policy-authoring-skills-all.zip   : bundle of the individual zips + UPLOAD_HOWTO.txt
#   - policy-authoring-skills-codex.zip : full skill folders INCLUDING agents/ — for ~/.agents/skills copy
# Pure bash + zip (macOS bash 3.2 compatible). Run from anywhere. HOWTO txts are editorial (not generated).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SK="$ROOT/plugins/policy-authoring/skills"
DIST="$ROOT/dist"

SKILLS=()
for d in "$SK"/*/; do SKILLS+=("$(basename "$d")"); done
echo "skills (${#SKILLS[@]}): ${SKILLS[*]}"

rm -f "$DIST"/*.zip   # regenerate all zips (keep *.txt HOWTOs)

# individual claude.ai skill zips (exclude agents/, which is Codex-only)
for s in "${SKILLS[@]}"; do
  ( cd "$SK" && zip -rqX "$DIST/$s.zip" "$s" -x "$s/agents/*" )
done

# Codex bundle: full skill folders incl agents/
( cd "$SK" && zip -rqX "$DIST/policy-authoring-skills-codex.zip" "${SKILLS[@]}" )

# all-in-one bundle: the individual zips + the upload howto
INDIV=()
for s in "${SKILLS[@]}"; do INDIV+=("$s.zip"); done
( cd "$DIST" && zip -qX policy-authoring-skills-all.zip "${INDIV[@]}" UPLOAD_HOWTO.txt )

echo "built $(ls "$DIST"/*.zip | wc -l | tr -d ' ') zips in $DIST"
