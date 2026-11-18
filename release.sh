#!/usr/bin/env bash
# Publishes a version. One command; it stops, with the reason, at the first thing that is not right,
# and nothing reaches GitHub before every check has passed.
#
#   bash release.sh 0.2.2          # check, set the version, commit, tag, push, wait for the installers
#   bash release.sh 0.2.2 --dry    # every check and the tests, then stop: nothing committed, nothing pushed
#   bash release.sh check 0.2.2    # later: are the three installers of v0.2.2 on the release page?
#
# Before running it, write by hand the two texts a person must write:
#   CHANGELOG.md                  one line that contains "Release v0.2.2"
#   packaging/release_notes.md    the text of the release page, which names the version
#
# What it checks, in this order
#   1. the branch is main, nothing is uncommitted, main equals GitHub's main, the tag is new
#   2. the two texts above name the version
#   3. no inventory data is tracked by git (factors, results, database files)
#   4. no commit since the last tag names another author, a co-author or an AI tool
#   5. in a fresh copy of the repository, with Windows line endings and new environments:
#      the version is set in the five files that state it, and every test passes, once with the
#      packages GitHub's test run installs and once with the ones the installer build installs
#   6. the paper builds and has at most 15 pages (skipped with a notice when LaTeX is not installed;
#      SKIP_PAPER=1 skips it on purpose)
# Then it sets the version here, commits, tags and pushes, and waits until GitHub has built the
# installers for macOS (Apple silicon and Intel) and Windows.
#
# docs/RUNBOOK.md lists what each failure means and what to do.
set -euo pipefail
cd "$(dirname "$0")"

AUTHOR_NAME="Ashira Benchimol"
INSTALLERS=("mac-apple-silicon.dmg" "mac-intel.dmg" "windows-setup.exe")
MAX_PAGES=15

say()  { printf '\n== %s\n' "$*"; }
stop() { printf '\nNOT PUBLISHED: %s\n' "$*" >&2; exit 1; }

slug() {   # owner/name of the GitHub repository behind origin, empty for any other remote
  git remote get-url origin 2>/dev/null | sed -nE 's#^(https://([^@/]+@)?github\.com/|git@github\.com:)([^/]+/[^/.]+)(\.git)?/?$#\3#p'
}

installers_published() {   # prints the names of the installers on the release page of tag $1
  python3 - "$1" "$(slug)" <<'PY'
import json, sys, urllib.request
tag, repo = sys.argv[1], sys.argv[2]
try:
    with urllib.request.urlopen(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", timeout=30) as r:
        print("\n".join(a["name"] for a in json.load(r).get("assets", [])))
except Exception:
    pass
PY
}

missing_installers() {
  local have; have="$(installers_published "$1")"
  local m=()
  for name in "${INSTALLERS[@]}"; do grep -q -- "$name" <<<"$have" || m+=("$name"); done
  echo "${m[*]:-}"
}

set_version() {   # writes version $1 into the five files that state it, in the repository at $2
  python3 - "$1" "$2" <<'PY'
import os, re, sys
version, root = sys.argv[1], sys.argv[2]
places = [
    ("pyproject.toml",         r'(?m)^(version = ")[^"]+(")'),
    ("branch/__init__.py",     r'(?m)^(__version__ = ")[^"]+(")'),
    ("CITATION.cff",           r'(?m)^(version: )\S+()'),
    ("packaging/windows.iss",  r'(?m)^(#define Version ")[^"]+(")'),
    ("packaging/branch.spec",  r'("CFBundleShortVersionString": ")[^"]+(")'),
]
for name, pattern in places:
    path = os.path.join(root, name)
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    new, n = re.subn(pattern, lambda m: m.group(1) + version + m.group(2), text)
    if n != 1:
        sys.exit(f"{name}: expected one place that states the version, found {n}")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
PY
}

# ---------------------------------------------------------------- check VERSION
if [[ "${1:-}" == "check" ]]; then
  [[ -n "${2:-}" ]] || stop "say which version: bash release.sh check 0.2.2"
  m="$(missing_installers "v$2")"
  if [[ -z "$m" ]]; then echo "v$2: the three installers are on the release page."; exit 0; fi
  echo "v$2: not on the release page yet: $m"
  echo "See https://github.com/$(slug)/actions. A job that failed or was cancelled: open the run, Re-run failed jobs."
  exit 1
fi

VERSION="${1:-}"
DRY=0; [[ "${2:-}" == "--dry" ]] && DRY=1
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || stop "give the version as three numbers: bash release.sh 0.2.2"
TAG="v$VERSION"

say "1. state of the repository"
[[ "$(git rev-parse --abbrev-ref HEAD)" == "main" ]] || stop "you are on the branch $(git rev-parse --abbrev-ref HEAD); releases leave from main (git checkout main)"
[[ -z "$(git status --porcelain)" ]] || stop "there are uncommitted changes (git status shows them)"
git fetch --quiet --tags origin
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || stop "main here differs from main on GitHub (git pull, or git push origin main, then run again)"
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null && stop "the tag $TAG exists already; choose the next number"
[[ -n "$(git ls-remote --tags origin "$TAG")" ]] && stop "the tag $TAG exists on GitHub already"
echo "main, clean, equal to GitHub, $TAG is new"

say "2. the texts a person writes"
grep -q "Release $TAG" CHANGELOG.md || stop "CHANGELOG.md has no line with \"Release $TAG\""
grep -q "$VERSION" packaging/release_notes.md || stop "packaging/release_notes.md does not name version $VERSION"
echo "CHANGELOG.md and packaging/release_notes.md name $VERSION"

say "3. no inventory data in git"
bad="$(git ls-files | grep -E '^(results|data/factors|data/factors_second)/|\.zolca$' || true)"
[[ -z "$bad" ]] || stop "these files must not be in git: $bad"
echo "none"

say "4. authorship of the commits since the last tag"
last="$(git describe --tags --abbrev=0 2>/dev/null || true)"
range="${last:+$last..}HEAD"
others="$(git log "$range" --format='%h %an <%ae> / %cn <%ce>' | grep -v -E "^[0-9a-f]+ $AUTHOR_NAME <([^>]*@users\.noreply\.github\.com)?> / ($AUTHOR_NAME <([^>]*@users\.noreply\.github\.com)?>|GitHub <noreply@github\.com>)$" || true)"
[[ -z "$others" ]] || stop "commits with another author or a visible e-mail address: $others"
marks="$(git log "$range" --format='%h %B' | grep -i -E 'co-authored-by|generated with|claude|anthropic|chatgpt|copilot' || true)"
[[ -z "$marks" ]] || stop "commit messages that name a co-author or an AI tool: $marks"
echo "every commit since ${last:-the beginning} is by $AUTHOR_NAME, with no address"

say "5. fresh copy, Windows line endings, new environment, version $VERSION, all tests"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
git -c core.autocrlf=true clone --quiet . "$TMP/copy"
set_version "$VERSION" "$TMP/copy"
python3 -m venv "$TMP/env"
{ "$TMP/env/bin/python" -m pip install --quiet --upgrade pip &&
  (cd "$TMP/copy" && "$TMP/env/bin/python" -m pip install --quiet -e ".[dev,experiments,app]"); } >"$TMP/install.log" 2>&1 \
  || { cat "$TMP/install.log"; stop "the installation fails in a new environment (the log is above)"; }
(cd "$TMP/copy" && "$TMP/env/bin/python" -m pytest -q) || stop "tests fail in a fresh copy (they may pass here because of files that are not in git)"
echo "installed as a package, away from the repository: the data travels with it and a comparison runs"
(cd "$TMP/copy" && "$TMP/env/bin/python" -m pip wheel --quiet --no-deps -w "$TMP/wheel" . >"$TMP/wheel.log" 2>&1) \
  || { cat "$TMP/wheel.log"; stop "the package does not build"; }
"$TMP/env/bin/python" -m pip install --quiet --no-deps --target "$TMP/site" "$TMP"/wheel/*.whl
(cd "$TMP" && PYTHONPATH="$TMP/site" "$TMP/env/bin/python" - <<'PY'
import os, branch
from branch.paths import RUNTIME_DATA, data_path
from branch.builder import build_model
from branch.demo_factors import demo_factors
assert "site" in branch.__file__ and "copy" not in branch.__file__, branch.__file__
for sub in RUNTIME_DATA:
    assert os.listdir(data_path(sub)), sub
model = build_model("pet_bottle_1l", "glass_refillable_1l", "PT", factors=demo_factors())
print(f"  {len(model.choices)} choices, {len(model.terms)} terms, data in {data_path()}")
PY
) || stop "the installed package does not find its data (branch/paths.py, pyproject.toml)"
echo "the same tests with the packages of the installer build"
python3 -m venv "$TMP/env2"
{ "$TMP/env2/bin/python" -m pip install --quiet --upgrade pip &&
  (cd "$TMP/copy" && "$TMP/env2/bin/python" -m pip install --quiet -e ".[app,olca,report]" pytest); } >"$TMP/install2.log" 2>&1 \
  || { cat "$TMP/install2.log"; stop "the installation of the installer build fails (the log is above)"; }
(cd "$TMP/copy" && "$TMP/env2/bin/python" -m pytest -q) || stop "tests fail with the packages of the installer build (.github/workflows/installers.yml)"

say "6. the paper"
if [[ "${SKIP_PAPER:-0}" == "1" ]]; then
  echo "skipped on purpose (SKIP_PAPER=1)"
elif command -v latexmk >/dev/null 2>&1 && command -v pdfinfo >/dev/null 2>&1; then
  (cd "$TMP/copy/paper" && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex >/dev/null 2>&1) || stop "the paper does not build from a fresh copy (cd paper && latexmk -pdf main.tex shows why)"
  pages="$(pdfinfo "$TMP/copy/paper/main.pdf" | awk '/^Pages/ {print $2}')"
  [[ "$pages" -le "$MAX_PAGES" ]] || stop "the paper has $pages pages; the limit is $MAX_PAGES"
  echo "builds, $pages pages"
else
  echo "NOT CHECKED: LaTeX (latexmk, pdfinfo) is not installed on this computer"
fi

if [[ "$DRY" == "1" ]]; then
  say "dry run: every check passed; nothing was committed or pushed"
  exit 0
fi

say "7. version, commit, tag, push"
set_version "$VERSION" .
if [[ -n "$(git status --porcelain)" ]]; then
  git add pyproject.toml branch/__init__.py CITATION.cff packaging/windows.iss packaging/branch.spec
  GIT_COMMITTER_NAME="$AUTHOR_NAME" GIT_COMMITTER_EMAIL="" git commit --quiet --author="$AUTHOR_NAME <>" -m "Version $VERSION"
fi
GIT_COMMITTER_NAME="$AUTHOR_NAME" GIT_COMMITTER_EMAIL="" git tag "$TAG"
git push --quiet origin main
git push --quiet origin "$TAG"
echo "pushed main and $TAG"

REPO="$(slug)"
if [[ -z "$REPO" ]]; then
  say "done (origin is not GitHub, so there are no installers to wait for)"
  exit 0
fi
say "8. waiting for GitHub to build the three installers (it has taken from 5 to 45 minutes; Ctrl C stops the waiting, not the build)"
echo "https://github.com/$REPO/actions"
for minute in $(seq 1 45); do
  sleep 60
  m="$(missing_installers "$TAG")"
  [[ -z "$m" ]] && { say "PUBLISHED: $TAG, three installers, https://github.com/$REPO/releases/tag/$TAG"; exit 0; }
  (( minute % 5 == 0 )) && echo "  $minute min, still missing: $m"
done
echo
echo "After 45 minutes these are still missing: $m"
echo "Open https://github.com/$REPO/actions, open the run of $TAG and choose Re-run failed jobs. Then: bash release.sh check $VERSION"
exit 1
