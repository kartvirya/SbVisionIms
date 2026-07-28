/**
 * B.S. / A.D. date entry synced to hidden fields (DD-MM-YYYY display, validation hints).
 */
(function (window) {
    var DEFAULT_TIME = "12:00";
    var BS_MONTHS = [
        "Baisakh", "Jestha", "Asar", "Shrawan", "Bhadra", "Aswin",
        "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
    ];
    var AD_MONTHS = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ];

    function pad(n) {
        return String(n).padStart(2, "0");
    }

    function getNepaliDateClass() {
        return window.NepaliDate && window.NepaliDate.default ? window.NepaliDate.default : null;
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

    function parseHiddenDate(value) {
        if (!value) {
            return null;
        }
        var raw = String(value).trim();
        var datePart = raw.split("T")[0];
        return parseYmdParts(datePart.split(/[-/]/));
    }

    /** Accept DD-MM-YYYY, DD/MM/YYYY, or legacy YYYY-MM-DD. */
    function parseDisplayInput(value) {
        if (!value) {
            return null;
        }
        var parts = String(value).trim().split(/[-/.]/).filter(Boolean);
        if (parts.length !== 3) {
            return null;
        }
        var first = Number(parts[0]);
        var second = Number(parts[1]);
        var third = Number(parts[2]);
        if (!first || !second || !third) {
            return null;
        }
        if (String(parts[0]).length >= 4 && first > 31) {
            return parseYmdParts(parts);
        }
        if (String(parts[2]).length >= 4 || third > 31) {
            return { year: third, month: second, day: first };
        }
        return parseYmdParts(parts);
    }

    function ymdToDisplay(ymd) {
        if (!ymd) {
            return "";
        }
        return pad(ymd.day) + "-" + pad(ymd.month) + "-" + ymd.year;
    }

    function ymdToIso(ymd) {
        if (!ymd) {
            return "";
        }
        return ymd.year + "-" + pad(ymd.month) + "-" + pad(ymd.day);
    }

    function formatHiddenDate(ad) {
        if (!ad) {
            return "";
        }
        return ymdToIso(ad) + "T" + DEFAULT_TIME;
    }

    function hiddenDateToBsIso(hiddenValue) {
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
        var ymd = parseDisplayInput(bsValue);
        if (!ymd) {
            return "";
        }
        try {
            var nd = ND.parse(ymdToIso(ymd));
            var js = nd.toJsDate();
            return formatHiddenDate({
                year: js.getFullYear(),
                month: js.getMonth() + 1,
                day: js.getDate(),
            });
        } catch (err) {
            return "";
        }
    }

    function formatBsReadable(isoBs) {
        var ymd = parseYmdParts(String(isoBs || "").split(/[-/]/));
        if (!ymd) {
            return "";
        }
        return ymd.day + " " + BS_MONTHS[ymd.month - 1] + " " + ymd.year;
    }

    function formatAdReadable(ad) {
        if (!ad) {
            return "";
        }
        return ad.day + " " + AD_MONTHS[ad.month - 1] + " " + ad.year;
    }

    function isValidAdYmd(ad) {
        if (!ad) {
            return false;
        }
        var d = new Date(ad.year, ad.month - 1, ad.day);
        return (
            d.getFullYear() === ad.year &&
            d.getMonth() === ad.month - 1 &&
            d.getDate() === ad.day
        );
    }

    function maskDateInput(el) {
        var digits = String(el.value || "").replace(/\D/g, "").slice(0, 8);
        if (digits.length <= 2) {
            el.value = digits;
        } else if (digits.length <= 4) {
            el.value = digits.slice(0, 2) + "-" + digits.slice(2);
        } else {
            el.value = digits.slice(0, 2) + "-" + digits.slice(2, 4) + "-" + digits.slice(4);
        }
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

    function setValidationState(wrap, result) {
        var mode = currentCal(wrap);
        var input = wrap.querySelector(mode === "bs" ? ".nepali-bs-date" : ".nepali-ad-date");
        var errorEl = wrap.querySelector(".nepali-date-error");
        var hint = wrap.querySelector(".nepali-ad-hint");
        if (input) {
            input.classList.toggle("is-invalid", !result.valid);
            input.setAttribute("aria-invalid", result.valid ? "false" : "true");
        }
        if (errorEl) {
            errorEl.textContent = result.valid ? "" : result.message;
            errorEl.classList.toggle("d-none", result.valid || !result.message);
        }
        if (hint) {
            hint.classList.toggle("text-danger", !result.valid);
            hint.classList.toggle("text-muted", result.valid);
        }
        wrap.dataset.dateValid = result.valid ? "1" : "0";
    }

    function validateWrap(wrap) {
        var mode = currentCal(wrap);
        var input = wrap.querySelector(mode === "bs" ? ".nepali-bs-date" : ".nepali-ad-date");
        var val = input ? String(input.value || "").trim() : "";
        if (!val) {
            return { valid: false, message: "Enter date as DD-MM-YYYY" };
        }
        if (mode === "bs") {
            if (!bsToHiddenDate(val)) {
                return { valid: false, message: "Invalid B.S. date — check day, month, year" };
            }
            return { valid: true, message: "" };
        }
        var ad = parseDisplayInput(val);
        if (!ad || !isValidAdYmd(ad)) {
            return { valid: false, message: "Invalid A.D. date — use DD-MM-YYYY" };
        }
        return { valid: true, message: "" };
    }

    function updateHint(wrap, value, validation) {
        var hint = wrap.querySelector(".nepali-ad-hint");
        if (!hint) {
            return;
        }
        if (!validation.valid) {
            hint.textContent = validation.message;
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
        if (mode === "bs") {
            hint.textContent = "A.D. " + formatAdReadable(ad);
            return;
        }
        var bsIso = hiddenDateToBsIso(value);
        hint.textContent = bsIso ? "B.S. " + formatBsReadable(bsIso) : "";
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
                var ad = parseDisplayInput(adVal);
                hiddenValue = isValidAdYmd(ad) ? formatHiddenDate(ad) : "";
            }
        }
        var validation = validateWrap(wrap);
        if (!validation.valid) {
            if (!opts.allowClear && previous) {
                hiddenValue = previous;
            } else {
                hiddenValue = validation.valid ? hiddenValue : "";
            }
        }
        if (!hiddenValue && !opts.allowClear && previous && validation.valid) {
            hiddenValue = previous;
        }
        if (validation.valid) {
            writeHidden(wrap, hiddenValue);
        }
        setValidationState(wrap, validation);
        updateHint(wrap, hiddenValue || (validation.valid ? previous : ""), validation);
        return validation.valid;
    }

    function loadIntoVisible(wrap, hiddenValue) {
        var bsIso = hiddenDateToBsIso(hiddenValue);
        var bsYmd = parseYmdParts(bsIso ? bsIso.split(/[-/]/) : null);
        var ad = parseHiddenDate(hiddenValue);
        var bsInput = wrap.querySelector(".nepali-bs-date");
        var adInput = wrap.querySelector(".nepali-ad-date");
        if (bsInput) {
            bsInput.value = bsYmd ? ymdToDisplay(bsYmd) : "";
            bsInput.removeAttribute("readonly");
        }
        if (adInput) {
            adInput.value = ad ? ymdToDisplay(ad) : "";
        }
        var validation = validateWrap(wrap);
        setValidationState(wrap, validation);
        updateHint(wrap, hiddenValue, validation);
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
            el.addEventListener("input", function () {
                maskDateInput(el);
                syncFromVisible(wrap, { allowClear: true });
            });
            el.addEventListener("change", function () {
                syncFromVisible(wrap, { allowClear: true });
            });
            el.addEventListener("blur", function () {
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
            document.querySelectorAll(".nepali-datetime-wrap").forEach(function (wrap) {
                syncFromVisible(wrap, { allowClear: true });
            });
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
        isWrapValid: function (wrap) {
            if (typeof wrap === "string") {
                wrap = document.querySelector(wrap);
            }
            if (!wrap) {
                return false;
            }
            return validateWrap(wrap).valid;
        },
        reloadWrap: function (wrap) {
            if (typeof wrap === "string") {
                wrap = document.querySelector(wrap);
            }
            if (wrap) {
                loadIntoVisible(wrap, readHidden(wrap));
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
