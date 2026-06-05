function stockAdjustUrl(itemId) {
    var tpl = window.STOCK_ADJUST_URL_TPL || '/product/__ID__/adjust-stock/';
    return tpl.replace('__ID__', itemId);
}

function openStockAdjustModal(itemId, itemName) {
    var modalEl = document.getElementById('stockAdjustModal');
    var bodyEl = document.getElementById('stockAdjustModalBody');
    var titleEl = document.getElementById('stockAdjustModalTitle');
    if (!modalEl || !bodyEl) {
        window.location.href = stockAdjustUrl(itemId);
        return;
    }
    if (titleEl) {
        titleEl.textContent = 'Adjust stock — ' + (itemName || 'Product');
    }
    bodyEl.innerHTML = '<div class="text-center p-4 text-muted">Loading…</div>';
    var nextUrl = encodeURIComponent(window.location.pathname + window.location.search);
    fetch(stockAdjustUrl(itemId) + '?next=' + nextUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
    })
        .then(function (r) {
            if (!r.ok) throw new Error('Failed to load form');
            return r.text();
        })
        .then(function (html) {
            bodyEl.innerHTML = html;
            if (window.bootstrap && bootstrap.Modal) {
                bootstrap.Modal.getOrCreateInstance(modalEl).show();
            }
        })
        .catch(function () {
            bodyEl.innerHTML = '<div class="alert alert-danger mb-0">Could not load adjustment form.</div>';
        });
}
