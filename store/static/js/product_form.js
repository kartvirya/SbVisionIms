/**
 * Supplier → brand cascade on product create/update forms.
 */
(function () {
  function initProductForm() {
    var vendorSelect = document.getElementById("id_vendor");
    var brandSelect = document.getElementById("id_brand");
    if (!vendorSelect || !brandSelect) {
      return;
    }

    var brandsUrlTemplate = vendorSelect.dataset.brandsUrl;
    if (!brandsUrlTemplate) {
      return;
    }

    var selectedBrand = brandSelect.dataset.selectedBrand || "";

    function setBrandOptions(brands, keepValue) {
      var current = keepValue ? brandSelect.value : "";
      brandSelect.innerHTML = "";
      var placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = brands.length ? "Select brand" : "No brands for this supplier";
      brandSelect.appendChild(placeholder);
      brands.forEach(function (b) {
        var opt = document.createElement("option");
        opt.value = String(b.id);
        opt.textContent = b.name;
        brandSelect.appendChild(opt);
      });
      brandSelect.disabled = brands.length === 0;
      if (current && brands.some(function (b) { return String(b.id) === current; })) {
        brandSelect.value = current;
      }
    }

    function loadBrands(vendorId, keepValue) {
      if (!vendorId) {
        brandSelect.disabled = true;
        setBrandOptions([], false);
        return;
      }
      brandSelect.disabled = true;
      var url = brandsUrlTemplate.replace("/0/", "/" + vendorId + "/");
      fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { return r.json(); })
        .then(function (data) { setBrandOptions(data || [], keepValue); })
        .catch(function () { setBrandOptions([], false); });
    }

    vendorSelect.addEventListener("change", function () {
      loadBrands(vendorSelect.value, false);
    });

    if (selectedBrand) {
      brandSelect.dataset.selectedBrand = selectedBrand;
    }
    if (vendorSelect.value) {
      loadBrands(vendorSelect.value, true);
    } else {
      brandSelect.disabled = true;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initProductForm);
  } else {
    initProductForm();
  }
})();
