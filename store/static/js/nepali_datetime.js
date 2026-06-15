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
        return parseYmdParts(datePart.split(/[-/]/));
    }

    function parseYmdParts(parts) {
        if (!parts || parts.length !== 3) {
            return null;
        }
        var year = Number(String(parts[0]).trim());
        var month = Number(String(parts[1]).trim());
        var day = Number(String(parts[2]).trim());
        if (!year || !month || !day || month < 1 || month > 12 || day < 1 || day > 31) {
            return null;
        }
        return { year: year, month: month, day: day };
    }

    function parseAdTextInput(value) {
        if (!value) {
            return null;
        }
        return parseYmdParts(String(value).trim().split(/[-/]/));
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
        var formId = wrap.dataset.dateForm;
        if (formId) {
            var linkedForm = document.getElementById(formId);
            if (linkedForm) {
                var linked = linkedForm.querySelector("#" + CSS.escape(id));
                if (linked) {
                    return linked;
                }
            }
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

    function syncFromVisible(wrap, opts) {
        opts = opts || {};
        var mode = currentCal(wrap);
        var previous = readHidden(wrap);
        var hiddenValue = "";
        if (mode === "bs") {
            var bsInput = wrap.querySelector(".nepali-bs-date");
            var bsVal = bsInput ? String(bsInput.value || "").trim() : "";
            hiddenValue = bsVal ? bsToHiddenDate(bsVal) : "";
        } else {
            var adInput = wrap.querySelector(".nepali-ad-date");
            var adVal = adInput ? String(adInput.value || "").trim() : "";
            if (adVal) {
                var ad = parseAdTextInput(adVal);
                hiddenValue = ad ? formatHiddenDate(ad) : "";
            }
        }
        if (!hiddenValue && !opts.allowClear && previous) {
            hiddenValue = previous;
        }
        writeHidden(wrap, hiddenValue);
        updateHint(wrap, hiddenValue || previous);
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

        wrap.querySelectorAll(".nepali-bs-date, .nepali-ad-date").forEach(function (el) {
            el.addEventListener("change", function () {
                syncFromVisible(wrap, { allowClear: true });
            });
            el.addEventListener("input", function () {
                syncFromVisible(wrap, { allowClear: true });
            });
        });

        wrap.querySelectorAll(".nepali-cal-toggle [data-cal]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                syncFromVisible(wrap, { allowClear: true });
                var hiddenValue = readHidden(wrap);
                setCalMode(wrap, btn.dataset.cal);
                loadIntoVisible(wrap, hiddenValue);
            });
        });
    }

    function syncForm(form) {
        if (!form) {
            return;
        }
        var formId = form.id || "";
        document.querySelectorAll(".nepali-datetime-wrap").forEach(function (wrap) {
            if (wrap.dataset.dateForm === formId) {
                syncFromVisible(wrap, { allowClear: true });
            }
        });
        form.querySelectorAll(".nepali-datetime-wrap").forEach(function (wrap) {
            syncFromVisible(wrap, { allowClear: true });
        });
    }

    var api = {
        initAll: function (selector) {
            document.querySelectorAll(selector || ".nepali-datetime-wrap").forEach(initWrap);
        },
        syncAll: function () {
            document.querySelectorAll(".nepali-datetime-wrap").forEach(syncFromVisible);
        },
        syncForm: syncForm,
        syncWrap: function (wrap) {
            if (typeof wrap === "string") {
                wrap = document.querySelector(wrap);
            }
            if (wrap) {
                syncFromVisible(wrap, { allowClear: true });
            }
        },
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
