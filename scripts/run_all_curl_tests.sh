#!/usr/bin/env bash
# Run local regression + full route smoke tests.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${1:-http://127.0.0.1:8000}"
USERNAME="${2:-qa_admin}"
PASSWORD="${3:-qa-pass-123}"

cd "$ROOT"
echo "=== Issue regression ==="
bash scripts/curl_issue_regression.sh "$BASE_URL" "$USERNAME" "$PASSWORD"
echo
echo "=== Route smoke ==="
bash curl_smoke_test.sh "$BASE_URL" "$USERNAME" "$PASSWORD"
echo
echo "All curl test suites passed."
