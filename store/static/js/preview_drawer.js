function openImsPreview(url, title) {
    var titleEl = document.getElementById('imsPreviewTitle');
    var bodyEl = document.getElementById('imsPreviewBody');
    if (!titleEl || !bodyEl) {
        window.location.href = url;
        return;
    }
    titleEl.textContent = title || 'Details';
    bodyEl.innerHTML = '<div class="text-center p-4 text-muted">Loading…</div>';
    var drawer = document.getElementById('imsPreviewDrawer');
    if (drawer && window.bootstrap && bootstrap.Offcanvas) {
        bootstrap.Offcanvas.getOrCreateInstance(drawer).show();
    }
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
        .then(function (r) {
            if (!r.ok) throw new Error('Preview failed');
            return r.text();
        })
        .then(function (html) { bodyEl.innerHTML = html; })
        .catch(function () {
            bodyEl.innerHTML = '<div class="alert alert-danger m-0">Could not load preview.</div>';
        });
}

function bindPreviewRows(selector, urlAttr) {
    document.querySelectorAll(selector).forEach(function (row) {
        row.addEventListener('click', function (e) {
            if (e.target.closest('a, button, input, .no-preview')) return;
            var url = row.getAttribute(urlAttr);
            var title = row.getAttribute('data-preview-title') || 'Details';
            if (url) openImsPreview(url, title);
        });
    });
}
