(function () {
  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function postUpdate(payload) {
    return fetch(window.SALES_INLINE_UPDATE_URL, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify(payload),
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) {
          throw new Error(data.message || 'Save failed');
        }
        return data;
      });
    });
  }

  function flashSaved(el) {
    if (!el) return;
    el.classList.add('border-success');
    setTimeout(function () {
      el.classList.remove('border-success');
    }, 1200);
  }

  function initSaleInlineEdits() {
    if (!window.SALES_INLINE_UPDATE_URL) return;

    document.querySelectorAll('.sale-inline-date').forEach(function (input) {
      input.addEventListener('change', function () {
        var el = this;
        postUpdate({
          field: 'date',
          sale_id: el.dataset.saleId,
          value: el.value,
        })
          .then(function () {
            flashSaved(el);
          })
          .catch(function (err) {
            alert(err.message || 'Could not save date.');
          });
      });
    });

    document.querySelectorAll('.sale-inline-payment').forEach(function (select) {
      var saleId = select.dataset.saleId;
      var paidInput = document.querySelector(
        '.sale-inline-paid[data-sale-id="' + saleId + '"]'
      );
      var row = select.closest('tr');

      function togglePaidInput() {
        if (!paidInput) return;
        if (select.value === 'T') {
          paidInput.classList.remove('d-none');
        } else {
          paidInput.classList.add('d-none');
        }
      }

      select.addEventListener('change', function () {
        togglePaidInput();
        var payload = {
          field: 'payment_status',
          sale_id: saleId,
          status: select.value,
        };
        if (select.value === 'T') {
          if (!paidInput || !paidInput.value) {
            paidInput && paidInput.focus();
            return;
          }
          payload.amount_paid = paidInput.value;
        }
        postUpdate(payload)
          .then(function (data) {
            flashSaved(select);
            if (row && data.amount_paid !== undefined) {
              var paidCell = row.querySelector('.sale-paid-cell');
              var unpaidCell = row.querySelector('.sale-unpaid-cell');
              if (paidCell) {
                paidCell.textContent = 'Rs ' + data.amount_paid;
              }
              if (unpaidCell) {
                var remaining = parseFloat(data.amount_remaining || '0');
                if (remaining > 0) {
                  unpaidCell.innerHTML =
                    '<span class="text-danger fw-semibold">Rs ' +
                    data.amount_remaining +
                    '</span>';
                } else {
                  unpaidCell.innerHTML = '<span class="text-muted">—</span>';
                }
              }
              if (paidInput && select.value !== 'T') {
                paidInput.value = data.amount_paid;
              }
            }
          })
          .catch(function (err) {
            alert(err.message || 'Could not save payment status.');
          });
      });

      if (paidInput) {
        paidInput.addEventListener('change', function () {
          if (select.value !== 'T') return;
          postUpdate({
            field: 'payment_status',
            sale_id: saleId,
            status: 'T',
            amount_paid: paidInput.value,
          })
            .then(function (data) {
              flashSaved(paidInput);
              if (row && data.amount_paid !== undefined) {
                var paidCell = row.querySelector('.sale-paid-cell');
                var unpaidCell = row.querySelector('.sale-unpaid-cell');
                if (paidCell) {
                  paidCell.textContent = 'Rs ' + data.amount_paid;
                }
                if (unpaidCell) {
                  var remaining = parseFloat(data.amount_remaining || '0');
                  if (remaining > 0) {
                    unpaidCell.innerHTML =
                      '<span class="text-danger fw-semibold">Rs ' +
                      data.amount_remaining +
                      '</span>';
                  }
                }
              }
            })
            .catch(function (err) {
              alert(err.message || 'Could not save amount paid.');
            });
        });
      }

      togglePaidInput();
    });

    document.querySelectorAll('.sale-inline-category').forEach(function (select) {
      select.addEventListener('change', function () {
        var el = this;
        postUpdate({
          field: 'item_category',
          detail_id: el.dataset.detailId,
          category_id: el.value,
        })
          .then(function () {
            flashSaved(el);
          })
          .catch(function (err) {
            alert(err.message || 'Could not save category.');
          });
      });
    });

    document.querySelectorAll('.sale-inline-brand').forEach(function (select) {
      select.addEventListener('change', function () {
        var el = this;
        postUpdate({
          field: 'item_brand',
          detail_id: el.dataset.detailId,
          brand_id: el.value,
        })
          .then(function () {
            flashSaved(el);
          })
          .catch(function (err) {
            alert(err.message || 'Could not save brand.');
          });
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSaleInlineEdits);
  } else {
    initSaleInlineEdits();
  }
})();
