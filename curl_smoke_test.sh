#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
USERNAME="${2:-qa_admin}"
PASSWORD="${3:-qa-pass-123}"
COOKIE_JAR="$(mktemp)"
LOGIN_PAGE="$(mktemp)"
FAILURES=0

cleanup() {
  rm -f "$COOKIE_JAR" "$LOGIN_PAGE"
}
trap cleanup EXIT

run_check() {
  local method="$1"
  local path="$2"
  local expected="$3"
  local payload="${4:-}"
  local url="${BASE_URL}${path}"
  local code

  if [[ "$method" == "GET" ]]; then
    code="$(curl -sS -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" "$url")"
  else
    code="$(curl -sS -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X "$method" \
      -H "Content-Type: application/x-www-form-urlencoded" --data "$payload" "$url")"
  fi

  if [[ "$code" =~ $expected ]]; then
    echo "PASS [$method] $path -> $code (expected: $expected)"
  else
    echo "FAIL [$method] $path -> $code (expected: $expected)"
    FAILURES=$((FAILURES + 1))
  fi
}

db_value() {
  local code="$1"
  uv run manage.py shell -c "$code" 2>/dev/null | tr -d '\r' | tail -n 1
}

echo "== Anonymous checks =="
run_check "GET" "/" "302|200"
run_check "GET" "/accounts/login/" "200"

echo
echo "== Login =="
curl -sS -c "$COOKIE_JAR" "${BASE_URL}/accounts/login/" -o "$LOGIN_PAGE"
CSRF_TOKEN="$(awk '$6 == "csrftoken" {print $7}' "$COOKIE_JAR" | tail -n 1)"
if [[ -z "${CSRF_TOKEN}" ]]; then
  echo "FAIL Could not retrieve CSRF token for login"
  exit 1
fi

LOGIN_PAYLOAD="username=${USERNAME}&password=${PASSWORD}&csrfmiddlewaretoken=${CSRF_TOKEN}"
LOGIN_CODE="$(curl -sS -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -e "${BASE_URL}/accounts/login/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "$LOGIN_PAYLOAD" \
  "${BASE_URL}/accounts/login/")"
if [[ "$LOGIN_CODE" =~ 302|200 ]]; then
  echo "PASS [POST] /accounts/login/ -> $LOGIN_CODE"
else
  echo "FAIL [POST] /accounts/login/ -> $LOGIN_CODE"
  exit 1
fi

echo
echo "== Authenticated GET checks =="
# store
run_check "GET" "/" "200"
run_check "GET" "/products/" "200"
run_check "GET" "/new-product/" "200"
run_check "GET" "/search/" "200"
run_check "GET" "/deliveries/" "200"
run_check "GET" "/new-delivery/" "200"
run_check "GET" "/categories/" "200"
run_check "GET" "/categories/create/" "200"

# accounts
run_check "GET" "/accounts/profile/" "200"
run_check "GET" "/accounts/profile/update/" "200"
run_check "GET" "/accounts/profiles/" "200"
run_check "GET" "/accounts/new-profile/" "200|302"
run_check "GET" "/accounts/customers/" "200"
run_check "GET" "/accounts/customers/create/" "200"
run_check "GET" "/accounts/vendors/" "200"
run_check "GET" "/accounts/vendors/new/" "200"
run_check "GET" "/accounts/logistics/" "200"
run_check "GET" "/accounts/logistics/new/" "200"

# /accounts/get_customers/ is POST + AJAX only
CUSTOMERS_CODE="$(curl -sS -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -X POST -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "term=a" \
  "${BASE_URL}/accounts/get_customers/")"
if [[ "$CUSTOMERS_CODE" =~ 200 ]]; then
  echo "PASS [POST] /accounts/get_customers/ -> $CUSTOMERS_CODE (expected: 200)"
else
  echo "FAIL [POST] /accounts/get_customers/ -> $CUSTOMERS_CODE (expected: 200)"
  FAILURES=$((FAILURES + 1))
fi

# transactions
run_check "GET" "/transactions/sales/" "200"
run_check "GET" "/transactions/new-sale/" "200"
run_check "GET" "/transactions/purchases/" "200"
run_check "GET" "/transactions/new-purchase/" "200"
run_check "GET" "/transactions/sales/export/" "200"
run_check "GET" "/transactions/purchases/export/" "200"
run_check "GET" "/transactions/reports/stock-ledger/" "200"
run_check "GET" "/transactions/reports/payables-aging/" "200"

# invoice / bills
run_check "GET" "/invoice/invoices/" "200"
run_check "GET" "/invoice/new-invoice/" "200"
run_check "GET" "/bills/bills/" "200"
run_check "GET" "/bills/new-bill/" "200"

echo
echo "== Dynamic detail/update/delete checks =="
PRODUCT_SLUG="$(db_value "from store.models import Item; o=Item.objects.order_by('id').first(); print(o.slug if o else '')")"
DELIVERY_SLUG="$(db_value "from store.models import Delivery; o=Delivery.objects.order_by('id').first(); print(o.slug if o else '')")"
CATEGORY_ID="$(db_value "from store.models import Category; o=Category.objects.order_by('id').first(); print(o.id if o else '')")"

PURCHASE_SLUG="$(db_value "from transactions.models import Purchase; o=Purchase.objects.order_by('id').first(); print(o.slug if o else '')")"
PURCHASE_ID="$(db_value "from transactions.models import Purchase; o=Purchase.objects.order_by('id').first(); print(o.id if o else '')")"
SALE_ID="$(db_value "from transactions.models import Sale; o=Sale.objects.order_by('id').first(); print(o.id if o else '')")"

INVOICE_SLUG="$(db_value "from invoice.models import Invoice; o=Invoice.objects.order_by('id').first(); print(o.slug if o else '')")"
INVOICE_ID="$(db_value "from invoice.models import Invoice; o=Invoice.objects.order_by('id').first(); print(o.id if o else '')")"
BILL_SLUG="$(db_value "from bills.models import Bill; o=Bill.objects.order_by('id').first(); print(o.slug if o else '')")"
BILL_ID="$(db_value "from bills.models import Bill; o=Bill.objects.order_by('id').first(); print(o.id if o else '')")"

PROFILE_ID="$(db_value "from accounts.models import Profile; o=Profile.objects.order_by('id').first(); print(o.id if o else '')")"
CUSTOMER_ID="$(db_value "from accounts.models import Customer; o=Customer.objects.order_by('id').first(); print(o.id if o else '')")"
VENDOR_ID="$(db_value "from accounts.models import Vendor; o=Vendor.objects.order_by('id').first(); print(o.id if o else '')")"
LOGISTICS_ID="$(db_value "from accounts.models import Logistics; o=Logistics.objects.order_by('id').first(); print(o.id if o else '')")"

if [[ -n "$PRODUCT_SLUG" ]]; then
  run_check "GET" "/product/${PRODUCT_SLUG}/" "200"
  run_check "GET" "/item/${PRODUCT_SLUG}/" "200"
  run_check "GET" "/product/${PRODUCT_SLUG}/update/" "200"
  run_check "GET" "/product/${PRODUCT_SLUG}/delete/" "200"
else
  echo "SKIP product detail/update/delete checks (no Item rows)"
fi

if [[ -n "$DELIVERY_SLUG" ]]; then
  run_check "GET" "/delivery/${DELIVERY_SLUG}/" "200"
else
  echo "SKIP delivery detail check (no Delivery rows)"
fi

if [[ -n "$CATEGORY_ID" ]]; then
  run_check "GET" "/categories/${CATEGORY_ID}/" "200"
  run_check "GET" "/categories/${CATEGORY_ID}/update/" "200"
  run_check "GET" "/categories/${CATEGORY_ID}/delete/" "200"
else
  echo "SKIP category detail/update/delete checks (no Category rows)"
fi

if [[ -n "$PURCHASE_SLUG" && -n "$PURCHASE_ID" ]]; then
  run_check "GET" "/transactions/purchase/${PURCHASE_SLUG}/" "200"
  run_check "GET" "/transactions/purchase/${PURCHASE_ID}/update/" "200"
  run_check "GET" "/transactions/purchase/${PURCHASE_ID}/delete/" "200"
else
  echo "SKIP purchase detail/update/delete checks (no Purchase rows)"
fi

if [[ -n "$SALE_ID" ]]; then
  run_check "GET" "/transactions/sale/${SALE_ID}/" "200"
  run_check "GET" "/transactions/sale/${SALE_ID}/delete/" "200"
else
  echo "SKIP sale detail/delete checks (no Sale rows)"
fi

if [[ -n "$INVOICE_SLUG" && -n "$INVOICE_ID" ]]; then
  run_check "GET" "/invoice/invoice/${INVOICE_SLUG}/" "200"
  run_check "GET" "/invoice/invoice/${INVOICE_SLUG}/update/" "200"
  run_check "GET" "/invoice/invoice/${INVOICE_ID}/delete/" "200"
else
  echo "SKIP invoice detail/update/delete checks (no Invoice rows)"
fi

if [[ -n "$BILL_SLUG" && -n "$BILL_ID" ]]; then
  run_check "GET" "/bills/bill/${BILL_SLUG}/update/" "200"
  run_check "GET" "/bills/bill/${BILL_ID}/delete/" "200"
else
  echo "SKIP bill update/delete checks (no Bill rows)"
fi

if [[ -n "$PROFILE_ID" ]]; then
  run_check "GET" "/accounts/profile/${PROFILE_ID}/update/" "200"
  run_check "GET" "/accounts/profile/${PROFILE_ID}/delete/" "200"
else
  echo "SKIP profile update/delete checks (no Profile rows)"
fi

if [[ -n "$CUSTOMER_ID" ]]; then
  run_check "GET" "/accounts/customers/${CUSTOMER_ID}/update/" "200"
  run_check "GET" "/accounts/customers/${CUSTOMER_ID}/delete/" "200"
else
  echo "SKIP customer update/delete checks (no Customer rows)"
fi

if [[ -n "$VENDOR_ID" ]]; then
  run_check "GET" "/accounts/vendors/${VENDOR_ID}/update/" "200"
  run_check "GET" "/accounts/vendors/${VENDOR_ID}/delete/" "200"
else
  echo "SKIP vendor update/delete checks (no Vendor rows)"
fi

if [[ -n "$LOGISTICS_ID" ]]; then
  run_check "GET" "/accounts/logistics/${LOGISTICS_ID}/update/" "200"
  run_check "GET" "/accounts/logistics/${LOGISTICS_ID}/delete/" "200"
else
  echo "SKIP logistics update/delete checks (no Logistics rows)"
fi

echo
if [[ "$FAILURES" -eq 0 ]]; then
  echo "All curl smoke checks passed."
else
  echo "Smoke checks finished with $FAILURES failure(s)."
  exit 1
fi
