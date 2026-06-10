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
      placeholder.textContent = "Select brand";
      brandSelect.appendChild(placeholder);
      brands.forEach(function (b) {
        var opt = document.createElement("option");
        opt.value = String(b.id);
        opt.textContent = b.name;
        brandSelect.appendChild(opt);
      });
      if (current && brands.some(function (b) { return String(b.id) === current; })) {
        brandSelect.value = current;
      }
    }

    function loadBrands(vendorId, keepValue) {
      if (!vendorId) {
        setBrandOptions([], false);
        return;
      }
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
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initProductForm);
  } else {
    initProductForm();
  }
})();
