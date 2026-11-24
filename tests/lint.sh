#!/bin/sh
# lint.sh: static checks, each tool in its own pinned container (only Docker is needed):
#   - shell scripts (POSIX sh): ShellCheck, warnings and errors
#   - Dockerfiles: hadolint
#   - Python test tools: ruff
#   - GitHub Actions workflows: actionlint
#   - relative links and anchors of the Markdown files: tests/check_docs.py
#   - secrets in the files: gitleaks
#
#   sh tests/lint.sh
# Exit code: number of failed tools.
set -u
cd "$(dirname "$0")/.." || exit 1
REPO=$(pwd -W 2>/dev/null || pwd)   # Git Bash on Windows: Docker needs a Windows path
export MSYS_NO_PATHCONV=1
run() { docker run --rm -v "$REPO:/src:ro" -w /src "$@"; }
ko=0
step() {
	name=$1; shift
	if "$@"; then echo "ok: $name"; else echo "FAILED: $name"; ko=$((ko + 1)); fi
}
step shellcheck run koalaman/shellcheck:v0.10.0 -s sh -S warning \
	gateway/entrypoint.sh gateway/gw-config gateway/gw-check tests/bench.sh tests/bench-inside.sh tests/lint.sh
# Not applied, on purpose:
#   DL3006  the base image is a build argument (UBUNTU=ubuntu:22.04), tagged there
#   DL3008  apt versions follow the Ubuntu release; pinning each would break at every update
#   DL4006  pipefail: the pipes end in "grep -q" or "grep -m1", which close the pipe early
step hadolint run hadolint/hadolint:v2.12.0 hadolint --ignore DL3006 --ignore DL3008 --ignore DL4006 \
	Dockerfile tests/Dockerfile.bench
# Test tools kept identical to the ones of the RutOS gateway: compact style accepted
#   E401 several imports on one line, E731 lambda assigned, E741 variable named "l"
step ruff run ghcr.io/astral-sh/ruff:0.6.9 check --no-cache --ignore E401,E731,E741 tests
if ls .github/workflows/*.yml >/dev/null 2>&1; then
	step actionlint run rhysd/actionlint:1.7.7 -no-color .github/workflows/*.yml
fi
step check_docs run python:3.12-slim python3 tests/check_docs.py
# Files only: the history of the public repository holds exported trees, each one checked before
# its commit
step gitleaks run zricethezav/gitleaks:v8.18.4 detect --no-git --source /src --redact --no-banner
[ "$ko" = 0 ] && echo "lint: all passed" || echo "lint: $ko tool(s) failed"
exit "$ko"
