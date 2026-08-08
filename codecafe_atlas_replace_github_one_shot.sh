#!/usr/bin/env bash
set -Eeuo pipefail

# CodeCafe Atlas — replace the GitHub repository with the verified clean source.
# Run from the ROOT of the WORKING public-clean source tree.
#
# This script does not contain the retired company name as a literal string.
# It invokes the source tree's own validate_public_identity.py before publishing.

REPO_URL="https://github.com/looplogic-dot-tech/codecafe-atlas.git"
BRANCH="main"
TAG="v1.0.24.15"
AUTHOR_NAME="Jaime Sánchez Sáenz"
AUTHOR_EMAIL="34150357+looplogic-dot-tech@users.noreply.github.com"

fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

printf '\n============================================================\n'
printf ' CodeCafe Atlas — ONE-SHOT GitHub clean replacement\n'
printf '============================================================\n\n'

# 1) Make sure this is the correct clean working source.
[[ -f main.py ]] || fail "main.py not found. Run this from the root of the working clean source."
[[ -d codecafe_atlas ]] || fail "codecafe_atlas/ not found."
[[ -f validate_public_identity.py ]] || fail "validate_public_identity.py not found."
[[ -f CODECAFE_ATLAS_IDENTITY.json ]] || fail "CODECAFE_ATLAS_IDENTITY.json not found."

printf '[1/9] Running the source package identity validator...\n'
python3 validate_public_identity.py

printf '[2/9] Checking that no operational database or build output will be published...\n'
DB_HITS="$(find . -type f \( -iname '*.db' -o -iname '*.sqlite' -o -iname '*.sqlite3' \) \
  -not -path './.git/*' -not -path './.venv/*' -not -path './venv/*' 2>/dev/null || true)"
[[ -z "$DB_HITS" ]] || { printf '%s\n' "$DB_HITS"; fail "Database file found in source tree. Remove it before publishing."; }

for d in dist build .venv venv __pycache__; do
  [[ ! -e "$d" ]] || fail "$d exists. Run this from a fresh clean SOURCE extraction, not a build directory."
done

SECRET_HITS="$(grep -RniI -E \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv --exclude-dir=build --exclude-dir=dist \
  '(github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----)' \
  . 2>/dev/null || true)"
[[ -z "$SECRET_HITS" ]] || { printf '%s\n' "$SECRET_HITS"; fail "Possible token/private key found."; }

# 3) Syntax validation. Use the project's pre-build validator only if its imports
# are available; the working build has already been user-tested.
printf '[3/9] Compile-checking Python source...\n'
python3 -m compileall -q main.py codecafe_atlas codecafe_atlas_updater.py make_update_package.py validate_public_identity.py validate_before_build.py

# 4) Make a safety archive OUTSIDE the repository.
printf '[4/9] Creating safety backup of this clean source...\n'
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="../CodeCafe_Atlas_before_GitHub_replace_${STAMP}.tar.gz"
tar --exclude='./.git' --exclude='./.venv' --exclude='./venv' --exclude='./build' --exclude='./dist' \
    --exclude='*/__pycache__' -czf "$BACKUP" .
printf 'Safety backup: %s\n' "$BACKUP"

# 5) Preserve any local Git metadata, then create an entirely new history.
printf '[5/9] Creating a brand-new clean Git history...\n'
if [[ -d .git ]]; then
    mv .git "../codecafe-atlas_previous_git_${STAMP}"
    printf 'Previous local .git preserved at ../codecafe-atlas_previous_git_%s\n' "$STAMP"
fi

git init -b "$BRANCH"
git config user.name "$AUTHOR_NAME"
git config user.email "$AUTHOR_EMAIL"

# Create a public-source .gitignore if this clean package does not already have one.
if [[ ! -f .gitignore ]]; then
cat > .gitignore <<'EOF'
# CodeCafe Atlas — public source exclusions
__pycache__/
*.py[cod]
.venv/
venv/
build/
dist/
*.spec
*.db
*.sqlite
*.sqlite3
.env
.env.*
.DS_Store
Thumbs.db
EOF
fi

git add -A

# The package validator is the canonical identity check. Run it AGAIN after
# creating .gitignore so the exact staged tree is still clean.
python3 validate_public_identity.py

# Refuse accidentally staged DB/build files.
if git ls-files | grep -E '(^|/)(build|dist|\.venv|venv)/|\.db$|\.sqlite3?$' >/dev/null; then
    git ls-files | grep -E '(^|/)(build|dist|\.venv|venv)/|\.db$|\.sqlite3?$' || true
    fail "A database/build/venv file is staged."
fi

git commit -m "CodeCafe Atlas v1.0.24.15 — clean public source"
git tag -a "$TAG" -m "CodeCafe Atlas $TAG"
git remote add origin "$REPO_URL"

printf '\n[6/9] DESTRUCTIVE STEP READY\n'
printf 'This will replace the GitHub main branch and %s tag with this new clean history.\n' "$TAG"
printf 'Repository: %s\n\n' "$REPO_URL"
read -r -p 'Type exactly: REPLACE GITHUB : ' CONFIRM
[[ "$CONFIRM" == "REPLACE GITHUB" ]] || fail "Cancelled."

# We intentionally bypass the machine's credential helper because it previously
# supplied incorrect cached GitHub credentials. At the Password prompt, the user
# must paste the fine-grained GitHub token.
GIT_AUTH=(env -u GIT_ASKPASS -u SSH_ASKPASS GIT_TERMINAL_PROMPT=1 git -c credential.helper=)

printf '\nWhen Git asks for Password, paste the GitHub fine-grained TOKEN (not the account password).\n\n'

printf '[7/9] Force-replacing GitHub main...\n'
"${GIT_AUTH[@]}" push --force origin "$BRANCH:$BRANCH"

printf '[8/9] Replacing GitHub release tag...\n'
"${GIT_AUTH[@]}" push origin ":refs/tags/$TAG" >/dev/null 2>&1 || true
"${GIT_AUTH[@]}" push --force origin "refs/tags/$TAG:refs/tags/$TAG"

printf '[9/9] Verifying remote branch and tag...\n'
LOCAL_MAIN="$(git rev-parse "$BRANCH")"
REMOTE_MAIN="$("${GIT_AUTH[@]}" ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}')"
LOCAL_TAG_COMMIT="$(git rev-parse "$TAG^{}")"
REMOTE_TAG_COMMIT="$("${GIT_AUTH[@]}" ls-remote origin "refs/tags/$TAG^{}" | awk '{print $1}')"
if [[ -z "$REMOTE_TAG_COMMIT" ]]; then
    REMOTE_TAG_COMMIT="$("${GIT_AUTH[@]}" ls-remote origin "refs/tags/$TAG" | awk '{print $1}')"
fi

[[ "$LOCAL_MAIN" == "$REMOTE_MAIN" ]] || fail "Remote main does not match the new clean commit."
[[ "$LOCAL_TAG_COMMIT" == "$REMOTE_TAG_COMMIT" ]] || fail "Remote tag does not match the clean release commit."

printf '\n============================================================\n'
printf ' SUCCESS\n'
printf '============================================================\n'
printf 'GitHub main has been replaced by the clean source.\n'
printf 'Clean root commit: %s\n' "$LOCAL_MAIN"
printf 'Tag %s now targets the clean release commit.\n' "$TAG"
printf '\nIf a GitHub Release page already exists for the old tag, inspect Releases once in the browser. Delete/recreate only the Release object if it still shows an obsolete description or uploaded asset. The branch/tag history itself has been replaced by this script.\n'
printf '\nOld unreachable Git objects may remain on GitHub servers until GitHub garbage-collects them; they are no longer reachable from main or this tag.\n'
