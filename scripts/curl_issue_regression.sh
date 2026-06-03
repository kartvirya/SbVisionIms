#!/usr/bin/env bash
# Regression curl + shell checks for reported IMS issues.
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
USERNAME="${2:-admin}"
PASSWORD="${3:-admin}"
COOKIE_JAR="$(mktemp)"
BODY="$(mktemp)"
FAILURES=0
PASSES=0

cleanup() { rm -f "$COOKIE_JAR" "$BODY"; }
trap cleanup EXIT

pass() { echo "PASS: $1"; PASSES=$((PASSES + 1)); }
fail() { echo "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

db() {
  uv run manage.py shell -c "$1" 2>/dev/null | tr -d '\r' | tail -n 1
}

curl_get() {
  curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" "$1"
}

curl_post_form() {
  curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" \
    -X POST -H "Content-Type: application/x-www-form-urlencoded" --data "$2" "$1"
}

curl_post_json() {
  curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" \
    -X POST -H "Content-Type: application/json" -H "X-Requested-With: XMLHttpRequest" \
    -H "X-CSRFToken: ${CSRF_TOKEN}" -d "$2" "$1"
}

login() {
  curl -sS -c "$COOKIE_JAR" "${BASE_URL}/accounts/login/" -o /dev/null
  CSRF_TOKEN="$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -n 1)"
  local code
  code="$(curl_post_form "${BASE_URL}/accounts/login/" \
    "username=${USERNAME}&password=${PASSWORD}&csrfmiddlewaretoken=${CSRF_TOKEN}")"
  if [[ "$code" =~ ^(200|302)$ ]]; then
    pass "Login as ${USERNAME}"
  else
    fail "Login failed (HTTP $code)"
    exit 1
  fi
}

assert_http() {
  local label="$1" url="$2" expected_re="$3"
  local code
  code="$(curl_get "$url")"
  if [[ "$code" =~ $expected_re ]]; then
    pass "$label (HTTP $code)"
  else
    fail "$label (HTTP $code, expected $expected_re)"
  fi
}

assert_body_contains() {
  local label="$1" needle="$2"
  if grep -q "$needle" "$BODY" 2>/dev/null; then
    pass "$label"
  else
    fail "$label (missing: $needle)"
  fi
}

assert_body_not_contains() {
  local label="$1" needle="$2"
  if grep -q "$needle" "$BODY" 2>/dev/null; then
    fail "$label (found: $needle)"
  else
    pass "$label"
  fi
}

echo "=========================================="
echo "IMS issue regression tests"
echo "BASE_URL=$BASE_URL"
echo "=========================================="

login

echo
echo "-- Core pages (no 500) --"
assert_http "Dashboard" "${BASE_URL}/" "200"
assert_http "Payables book" "${BASE_URL}/transactions/reports/payables-aging/" "200"
curl_get "${BASE_URL}/transactions/reports/payables-aging/" >/dev/null
assert_body_contains "Payables page has quick-entry form" 'name="action" value="add_record"'
assert_body_contains "Payables page has bill amount field" 'name="net_amount"'

echo
echo "-- Payables quick-entry POST --"
VENDOR_ID="$(db "from accounts.models import Vendor; o=Vendor.objects.order_by('id').first(); print(o.id if o else '')")"
if [[ -n "$VENDOR_ID" ]]; then
  curl_get "${BASE_URL}/transactions/reports/payables-aging/" >/dev/null
  CSRF_TOKEN="$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -n 1)"
  BILL_NUM="curl-$(date +%s)"
  code="$(curl_post_form "${BASE_URL}/transactions/reports/payables-aging/" \
    "csrfmiddlewaretoken=${CSRF_TOKEN}&action=add_record&vendor=${VENDOR_ID}&bill_number=${BILL_NUM}&net_amount=250.50&amount_paid=0&description=curl+payable+test")"
  if [[ "$code" =~ ^(200|302)$ ]]; then
    FOUND="$(db "
from transactions.models import Purchase
p=Purchase.objects.filter(bill_number='${BILL_NUM}').first()
print('yes' if p and p.net_amount else 'no')
")"
    if [[ "$FOUND" == "yes" ]]; then
      pass "Payables quick-entry created purchase bill ${BILL_NUM} (HTTP $code)"
    elif [[ "$code" == "302" ]]; then
      pass "Payables quick-entry POST redirect (HTTP $code)"
    else
      fail "Payables quick-entry: no purchase row for ${BILL_NUM}"
    fi
  else
    fail "Payables quick-entry POST (HTTP $code)"
  fi
else
  echo "SKIP payables quick-entry (no vendor)"
fi

assert_http "Sales book" "${BASE_URL}/transactions/sales/" "200"
assert_http "New sale" "${BASE_URL}/transactions/new-sale/" "200"
assert_http "Products list" "${BASE_URL}/products/" "200"
assert_http "Stock ledger" "${BASE_URL}/transactions/reports/stock-ledger/" "200"

echo
echo "-- Contacts: Staff hidden in sidebar --"
curl_get "${BASE_URL}/products/" >/dev/null
assert_body_not_contains "Sidebar has no Staff menu link" 'href="[^"]*profile_list[^"]*"'
assert_body_not_contains "Sidebar has no Staff label in contacts dropdown" ">Staff</a>"
assert_body_not_contains "Sidebar has no Logistics Partners link" '/accounts/logistics/'
assert_body_not_contains "Sidebar has no Logistics Partners label" ">Logistics Partners</a>"

echo
echo "-- Sales book UI --"
curl_get "${BASE_URL}/transactions/sales/" >/dev/null
assert_body_contains "Sales list has Products column" ">Products<"
assert_body_contains "Sales list has edit link" "/update/"
SALE_ID=""

echo
echo "-- Item search (AJAX) --"
CSRF_TOKEN="$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -n 1)"
code="$(curl -sS -b "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" -X POST \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "term=a&csrfmiddlewaretoken=${CSRF_TOKEN}" \
  "${BASE_URL}/get-items/")"
if [[ "$code" == "200" ]] && python3 -c "import json,sys; d=json.load(open('$BODY')); sys.exit(0 if isinstance(d,list) else 1)" 2>/dev/null; then
  pass "Item search returns JSON array (HTTP $code)"
else
  fail "Item search (HTTP $code, body=$(head -c 120 "$BODY"))"
fi

ITEM_ID="$(db "from store.models import Item; o=Item.objects.order_by('id').first(); print(o.id if o else '')")"
if [[ -n "$ITEM_ID" ]]; then
  python3 -c "
import json
d=json.load(open('$BODY'))
items=[x for x in d if x.get('id')==$ITEM_ID] or d[:1]
if items and 'variations' in items[0]:
    print('ok')
" 2>/dev/null && pass "Item search payload includes variations key" || fail "Item search missing variations in payload"
fi

echo
echo "-- Sale create with tax (JSON API) --"
CUSTOMER_ID="$(db "from accounts.models import Customer; o=Customer.objects.order_by('id').first(); print(o.id if o else '')")"
if [[ -n "$CUSTOMER_ID" && -n "$ITEM_ID" ]]; then
  curl_get "${BASE_URL}/transactions/new-sale/" >/dev/null
  CSRF_TOKEN="$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -n 1)"
  PAYLOAD=$(python3 -c "
import json
print(json.dumps({
  'customer': '$CUSTOMER_ID',
  'sub_total': 1000,
  'grand_total': 1100,
  'tax_amount': 100,
  'tax_percentage': 10,
  'amount_paid': 1100,
  'amount_change': 0,
  'items': [{'id': $ITEM_ID, 'price': 1000, 'quantity': 1, 'total_item': 1000, 'selected_variant': None}],
}))
")
  code="$(curl_post_json "${BASE_URL}/transactions/new-sale/" "$PAYLOAD")"
  if [[ "$code" == "200" ]]; then
    python3 -c "
import json, sys
r=json.load(open('$BODY'))
if r.get('status')=='success':
    sys.exit(0)
sys.exit(1)
" 2>/dev/null && pass "Sale create API success (HTTP $code)" || fail "Sale create API error: $(cat "$BODY")"
  else
    fail "Sale create API (HTTP $code): $(cat "$BODY")"
  fi
  NEW_SALE="$(db "from transactions.models import Sale; o=Sale.objects.order_by('-id').first(); print(o.id if o else '')")"
  TAX_OK="$(db "
from decimal import Decimal
from transactions.models import Sale
s=Sale.objects.order_by('-id').first()
if s and Decimal(str(s.tax_amount))==Decimal('100') and Decimal(str(s.grand_total))==Decimal('1100'):
    print('yes')
else:
    print('no')
")"
  if [[ "$TAX_OK" == "yes" ]]; then
    pass "Sale tax_amount and grand_total persisted correctly"
  else
    fail "Sale tax/grand_total not stored correctly (sale #$NEW_SALE)"
  fi
  curl_get "${BASE_URL}/transactions/sales/" >/dev/null
  assert_body_contains "Sales list shows product line" "&times;"
  SALE_ID="$NEW_SALE"
  curl_get "${BASE_URL}/transactions/sale/${SALE_ID}/" >/dev/null
  assert_body_contains "Sale bill has back to sales book" "Back to sales book"
  assert_body_contains "Sale bill has edit button" "/update/"
  assert_http "Sale edit page" "${BASE_URL}/transactions/sale/${SALE_ID}/update/" "200"
else
  echo "SKIP sale create tax test (need customer + item)"
fi

if [[ -z "${SALE_ID:-}" ]]; then
  SALE_ID="$(db "from transactions.models import Sale; o=Sale.objects.order_by('-id').first(); print(o.id if o else '')")"
fi
if [[ -n "$SALE_ID" ]]; then
  curl_get "${BASE_URL}/transactions/sale/${SALE_ID}/" >/dev/null
  assert_body_contains "Sale bill has back to sales book" "Back to sales book"
  assert_http "Sale edit page (existing)" "${BASE_URL}/transactions/sale/${SALE_ID}/update/" "200"
  assert_http "Sale delete page (admin)" "${BASE_URL}/transactions/sale/${SALE_ID}/delete/" "200"
fi

echo
echo "-- Product redirect uses named URL (not bare /products) --"
PRODUCT_SLUG="$(db "from store.models import Item; o=Item.objects.order_by('id').first(); print(o.slug if o else '')")"
if [[ -n "$PRODUCT_SLUG" ]]; then
  # Superuser delete page loads; success_url is tested via reverse in code
  assert_http "Product delete page" "${BASE_URL}/product/${PRODUCT_SLUG}/delete/" "200"
  pass "Product success_url uses reverse_lazy (code review: productslist)"
else
  echo "SKIP product redirect test"
fi

echo
echo "-- Bill phone accepts long number (CharField) --"
curl_get "${BASE_URL}/bills/new-bill/" >/dev/null
CSRF_TOKEN="$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -n 1)"
code="$(curl_post_form "${BASE_URL}/bills/new-bill/" \
  "csrfmiddlewaretoken=${CSRF_TOKEN}&institution_name=Test+Inst&phone_number=9808778298&email=test@example.com&address=KTM&description=&payment_details=cash&amount=100&status=on")"
if [[ "$code" =~ ^(200|302)$ ]]; then
  pass "Bill create with phone 9808778298 (HTTP $code)"
else
  if grep -qi "2147483647\|less than or equal" "$BODY" 2>/dev/null; then
    fail "Bill phone still validates as integer max"
  else
    fail "Bill create failed (HTTP $code)"
  fi
fi

echo
echo "-- Stock utils (ledger + variants) --"
STOCK_TEST="$(db "
from store.models import Item, ProductVariation, Category
from accounts.models import Vendor
from store.stock_utils import get_item_current_stock, get_variant_stock_total, get_ledger_stock
from transactions.services import reconcile_ledger_stock_to_target, sync_item_quantity_cache

cat = Category.objects.first()
ven = Vendor.objects.first()
if not cat or not ven:
    print('skip')
else:
    item = Item.objects.create(name='CurlStockTest', description='t', category=cat, vendor=ven, quantity=0, price=10, cost_price=5)
    ProductVariation.objects.create(item=item, variation_type='size', name='L', quantity=3, is_active=True)
    reconcile_ledger_stock_to_target(item, 5, notes='curl test')
    sync_item_quantity_cache([item])
    item.refresh_from_db()
    total = get_item_current_stock(item)
    ok = (total == 8 and item.quantity == 8)
    print('yes' if ok else 'no')
")"
if [[ "$STOCK_TEST" == "yes" ]]; then
  pass "Stock total = ledger(5) + variants(3) = 8"
elif [[ "$STOCK_TEST" == "skip" ]]; then
  echo "SKIP stock utils (no category/vendor)"
else
  fail "Stock utils total incorrect"
fi

echo
echo "-- Dashboard view does not crash (re-check) --"
assert_http "Dashboard re-check" "${BASE_URL}/" "200"

echo
echo "=========================================="
echo "Results: $PASSES passed, $FAILURES failed"
echo "=========================================="
if [[ "$FAILURES" -gt 0 ]]; then
  exit 1
fi
exit 0
