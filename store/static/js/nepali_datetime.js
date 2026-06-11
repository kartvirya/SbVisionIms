/**
 * B.S. / A.D. date entry synced to hidden fields for Django forms (date only, no popups).
 */
(function (window) {
    var DEFAULT_TIME = "12:00";

    function pad(n) {
        return String(n).padStart(2, "0");
    }

    function getNepaliDateClass() {
        return window.NepaliDate && window.NepaliDate.default ? window.NepaliDate.default : null;
    }

    function parseHiddenDate(value) {
        if (!value) {
            return null;
        }
        var raw = String(value).trim();
        var datePart = raw.split("T")[0];
        var ymd = datePart.split("-").map(Number);
        if (!ymd[0] || !ymd[1] || !ymd[2]) {
            return null;
        }
        return { year: ymd[0], month: ymd[1], day: ymd[2] };
    }

    function formatHiddenDate(ad) {
        if (!ad) {
            return "";
        }
        return ad.year + "-" + pad(ad.month) + "-" + pad(ad.day) + "T" + DEFAULT_TIME;
    }

    function hiddenDateToBs(hiddenValue) {
        var ND = getNepaliDateClass();
        var ad = parseHiddenDate(hiddenValue);
        if (!ND || !ad) {
            return "";
        }
        var nd = ND.fromAD(new Date(ad.year, ad.month - 1, ad.day));
        return nd.format("YYYY-MM-DD");
    }

    function bsToHiddenDate(bsValue) {
        var ND = getNepaliDateClass();
        if (!ND || !bsValue) {
            return "";
        }
        var nd = ND.parse(bsValue);
        var js = nd.toJsDate();
        return formatHiddenDate({
            year: js.getFullYear(),
            month: js.getMonth() + 1,
            day: js.getDate(),
        });
    }

    function currentCal(wrap) {
        return wrap.dataset.calMode || wrap.dataset.defaultCal || "bs";
    }

    function setCalMode(wrap, mode) {
        wrap.dataset.calMode = mode;
        var bsBlock = wrap.querySelector(".nepali-mode-bs");
        var adBlock = wrap.querySelector(".nepali-mode-ad");
        wrap.querySelectorAll(".nepali-cal-toggle [data-cal]").forEach(function (btn) {
            var isActive = btn.dataset.cal === mode;
            btn.classList.toggle("active", isActive);
            btn.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
        if (bsBlock) {
            bsBlock.classList.toggle("d-none", mode !== "bs");
            bsBlock.classList.toggle("hidden", mode !== "bs");
        }
        if (adBlock) {
            adBlock.classList.toggle("d-none", mode !== "ad");
            adBlock.classList.toggle("hidden", mode !== "ad");
        }
    }

    function findHidden(wrap) {
        var id = wrap.dataset.hidden;
        if (!id) {
            return null;
        }
        var form = wrap.closest("form");
        if (form) {
            var inForm = form.querySelector("#" + CSS.escape(id));
            if (inForm) {
                return inForm;
            }
        }
        return document.getElementById(id);
    }

    function readHidden(wrap) {
        var hidden = findHidden(wrap);
        return hidden ? hidden.value : "";
    }

    function writeHidden(wrap, value) {
        var hidden = findHidden(wrap);
        if (hidden) {
            hidden.value = value || "";
        }
    }

    function updateHint(wrap, value) {
        var hint = wrap.querySelector(".nepali-ad-hint");
        if (!hint) {
            return;
        }
        if (!value) {
            hint.textContent = "";
            return;
        }
        var mode = currentCal(wrap);
        var ad = parseHiddenDate(value);
        if (!ad) {
            hint.textContent = "";
            return;
        }
        var adText = pad(ad.year) + "-" + pad(ad.month) + "-" + pad(ad.day);
        if (mode === "bs") {
            hint.textContent = "A.D. " + adText;
            return;
        }
        var bs = hiddenDateToBs(value);
        hint.textContent = bs ? "B.S. " + bs : "";
    }

    function syncFromVisible(wrap) {
        var mode = currentCal(wrap);
        var hiddenValue = "";
        if (mode === "bs") {
            var bsInput = wrap.querySelector(".nepali-bs-date");
            hiddenValue = bsToHiddenDate(bsInput ? bsInput.value : "");
        } else {
            var adInput = wrap.querySelector(".nepali-ad-date");
            var ad = parseHiddenDate(adInput ? adInput.value + "T" + DEFAULT_TIME : "");
            hiddenValue = formatHiddenDate(ad);
        }
        writeHidden(wrap, hiddenValue);
        updateHint(wrap, hiddenValue);
    }

    function loadIntoVisible(wrap, hiddenValue) {
        var bs = hiddenDateToBs(hiddenValue);
        var ad = parseHiddenDate(hiddenValue);
        var bsInput = wrap.querySelector(".nepali-bs-date");
        var adInput = wrap.querySelector(".nepali-ad-date");
        if (bsInput) {
            bsInput.value = bs || bsInput.value || "";
            bsInput.removeAttribute("readonly");
        }
        if (adInput && ad) {
            adInput.value = pad(ad.year) + "-" + pad(ad.month) + "-" + pad(ad.day);
        } else if (adInput) {
            adInput.value = "";
        }
        updateHint(wrap, hiddenValue);
    }

    function initWrap(wrap) {
        if (wrap.dataset.nepaliInit === "1") {
            return;
        }
        var hidden = findHidden(wrap);
        if (!hidden) {
            return;
        }
        wrap.dataset.nepaliInit = "1";

        setCalMode(wrap, wrap.dataset.defaultCal || "bs");
        loadIntoVisible(wrap, hidden.value);
        syncFromVisible(wrap);

        wrap.querySelectorAll(".nepali-bs-date, .nepali-ad-date").forEach(function (el) {
            el.addEventListener("change", function () {
                syncFromVisible(wrap);
            });
            el.addEventListener("input", function () {
                syncFromVisible(wrap);
            });
        });

        wrap.querySelectorAll(".nepali-cal-toggle [data-cal]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                syncFromVisible(wrap);
                var hiddenValue = readHidden(wrap);
                setCalMode(wrap, btn.dataset.cal);
                loadIntoVisible(wrap, hiddenValue);
                syncFromVisible(wrap);
            });
        });
    }

    function syncForm(form) {
        if (!form) {
            return;
        }
        form.querySelectorAll(".nepali-datetime-wrap").forEach(syncFromVisible);
    }

    var api = {
        initAll: function (selector) {
            document.querySelectorAll(selector || ".nepali-datetime-wrap").forEach(initWrap);
        },
        syncAll: function () {
            document.querySelectorAll(".nepali-datetime-wrap").forEach(syncFromVisible);
        },
        syncForm: syncForm,
        setToday: function (hiddenId) {
            var wrap = document.querySelector('.nepali-datetime-wrap[data-hidden="' + hiddenId + '"]');
            if (!wrap) {
                return;
            }
            var now = new Date();
            var hiddenValue = formatHiddenDate({
                year: now.getFullYear(),
                month: now.getMonth() + 1,
                day: now.getDate(),
            });
            writeHidden(wrap, hiddenValue);
            loadIntoVisible(wrap, hiddenValue);
            syncFromVisible(wrap);
        },
    };

    window.ImsNepaliDatetime = api;
})(window);
