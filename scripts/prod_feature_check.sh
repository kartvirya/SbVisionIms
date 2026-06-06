#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${3:-}" && -z "${IMS_ADMIN_PASSWORD:-}" ]]; then
  echo "Usage: $0 [BASE_URL] [USERNAME] [PASSWORD]" >&2
  echo "Or set IMS_ADMIN_PASSWORD." >&2
  exit 1
fi

BASE_URL="${1:-https://sbvision.com.np/ims}"
BASE_URL="${BASE_URL%/}"
USERNAME="${2:-admin}"
PASSWORD="${3:-${IMS_ADMIN_PASSWORD:-}}"
COOKIE_JAR="$(mktemp)"
BODY="$(mktemp)"
PASSES=0
FAILURES=0

cleanup() { rm -f "$COOKIE_JAR" "$BODY"; }
trap cleanup EXIT

pass() { echo "PASS: $1"; PASSES=$((PASSES + 1)); }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

curl -sS -c "$COOKIE_JAR" "${BASE_URL}/accounts/login/" -o /dev/null
CSRF_TOKEN="$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -n 1)"
ENC_PASS="$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$PASSWORD'''))")"
code="$(curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/accounts/login/" \
  -H "Referer: ${BASE_URL}/accounts/login/" \
  --data "username=${USERNAME}&password=${ENC_PASS}&csrfmiddlewaretoken=${CSRF_TOKEN}")"
if [[ "$code" =~ ^(200|302)$ ]] && awk '$6=="sessionid"{found=1} END{exit !found}' "$COOKIE_JAR"; then
  pass "Login as ${USERNAME}"
else
  fail "Login failed (HTTP $code, no sessionid)"
  exit 1
fi

assert_page() {
  local label="$1" url="$2" needle="$3"
  local code
  code="$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" "$url")"
  if [[ "$code" == "200" ]] && grep -q "$needle" "$BODY"; then
    pass "$label"
  else
    fail "$label (HTTP $code, missing: $needle)"
  fi
}

echo "=========================================="
echo "Production new-feature checks"
echo "BASE_URL=$BASE_URL"
echo "=========================================="

assert_page "Sales book Payment column" "${BASE_URL}/transactions/sales/" "Payment"
assert_page "Sales book Unpaid column" "${BASE_URL}/transactions/sales/" "Unpaid"
assert_page "Products Adjust stock action" "${BASE_URL}/products/" "Adjust stock"
assert_page "Products stock adjust JS" "${BASE_URL}/products/" "stock_adjust.js"
assert_page "New sale payment method" "${BASE_URL}/transactions/new-sale/" "payment_method"
assert_page "Accounts book hub" "${BASE_URL}/accounts/accounts-book/" "Accounts Book"
assert_page "Accounts book customers tab" "${BASE_URL}/accounts/accounts-book/?tab=customers" "Balance due"
assert_page "Vendor account page" "${BASE_URL}/accounts/vendors/3/" "Transaction history"
assert_page "Stock ledger loads" "${BASE_URL}/transactions/reports/stock-ledger/" "ledger"

SALE_ID="$(ssh -o BatchMode=yes root@157.230.234.42 \
  "cd /var/www/inventory_ms && source venv/bin/activate && set -a && source .env && set +a && \
  python manage.py shell --settings=InventoryMS.settings_production -c \
  \"from transactions.models import Sale; print(Sale.objects.order_by('-id').first().id)\"" 2>/dev/null | tr -d '\r' | tail -n 1)"
if [[ -n "$SALE_ID" ]]; then
  assert_page "Sale return UI (sale #${SALE_ID})" "${BASE_URL}/transactions/sale/${SALE_ID}/" "Return all sold"
fi

echo "=========================================="
echo "Results: ${PASSES} passed, ${FAILURES} failed"
echo "=========================================="
exit $([[ "$FAILURES" -eq 0 ]] && echo 0 || echo 1)
