/**
 * B.S. / A.D. date entry synced to hidden datetime-local fields for Django forms.
 */
(function (window) {
    function pad(n) {
        return String(n).padStart(2, "0");
    }

    function getNepaliDateClass() {
        return window.NepaliDate && window.NepaliDate.default ? window.NepaliDate.default : null;
    }

    function parseAdDatetimeLocal(value) {
        if (!value) {
            return null;
        }
        const parts = value.split("T");
        const ymd = parts[0].split("-").map(Number);
        const hm = (parts[1] || "12:00").split(":").map(Number);
        return {
            year: ymd[0],
            month: ymd[1],
            day: ymd[2],
            hours: hm[0] || 0,
            minutes: hm[1] || 0,
        };
    }

    function formatAdDatetimeLocal(ad) {
        if (!ad) {
            return "";
        }
        return (
            ad.year +
            "-" +
            pad(ad.month) +
            "-" +
            pad(ad.day) +
            "T" +
            pad(ad.hours) +
            ":" +
            pad(ad.minutes)
        );
    }

    function adDatetimeLocalToBs(adValue) {
        const ND = getNepaliDateClass();
        const ad = parseAdDatetimeLocal(adValue);
        if (!ND || !ad) {
            return { bs: "", time: "12:00" };
        }
        const nd = ND.fromAD(new Date(ad.year, ad.month - 1, ad.day));
        return { bs: nd.format("YYYY-MM-DD"), time: pad(ad.hours) + ":" + pad(ad.minutes) };
    }

    function bsAndTimeToAdDatetimeLocal(bsValue, timeValue) {
        const ND = getNepaliDateClass();
        if (!ND || !bsValue) {
            return "";
        }
        const nd = ND.parse(bsValue);
        const js = nd.toJsDate();
        const time = timeValue || "12:00";
        const hm = time.split(":").map(Number);
        js.setHours(hm[0] || 0, hm[1] || 0, 0, 0);
        return formatAdDatetimeLocal({
            year: js.getFullYear(),
            month: js.getMonth() + 1,
            day: js.getDate(),
            hours: hm[0] || 0,
            minutes: hm[1] || 0,
        });
    }

    function currentCal(wrap) {
        return wrap.dataset.calMode || wrap.dataset.defaultCal || "bs";
    }

    function setCalMode(wrap, mode) {
        wrap.dataset.calMode = mode;
        const bsBlock = wrap.querySelector(".nepali-mode-bs");
        const adBlock = wrap.querySelector(".nepali-mode-ad");
        wrap.querySelectorAll(".nepali-cal-toggle [data-cal]").forEach(function (btn) {
            btn.classList.toggle("active", btn.dataset.cal === mode);
        });
        if (bsBlock) {
            bsBlock.classList.toggle("d-none", mode !== "bs");
        }
        if (adBlock) {
            adBlock.classList.toggle("d-none", mode !== "ad");
        }
    }

    function readHidden(wrap) {
        const hidden = document.getElementById(wrap.dataset.hidden);
        return hidden ? hidden.value : "";
    }

    function writeHidden(wrap, value) {
        const hidden = document.getElementById(wrap.dataset.hidden);
        if (hidden) {
            hidden.value = value || "";
        }
    }

    function updateHint(wrap, value) {
        const hint = wrap.querySelector(".nepali-ad-hint");
        if (!hint) {
            return;
        }
        if (!value) {
            hint.textContent = "";
            return;
        }
        const mode = currentCal(wrap);
        if (mode === "bs") {
            hint.textContent = "A.D. " + value.replace("T", " ");
            return;
        }
        const bs = adDatetimeLocalToBs(value);
        hint.textContent = bs.bs ? "B.S. " + bs.bs + " " + bs.time : "";
    }

    function syncFromVisible(wrap) {
        const mode = currentCal(wrap);
        let adValue = "";
        if (mode === "bs") {
            const bsInput = wrap.querySelector(".nepali-bs-date");
            const timeInput = wrap.querySelector(".nepali-bs-time");
            adValue = bsAndTimeToAdDatetimeLocal(
                bsInput ? bsInput.value : "",
                timeInput ? timeInput.value : ""
            );
        } else {
            const adInput = wrap.querySelector(".nepali-ad-datetime");
            adValue = adInput ? adInput.value : "";
        }
        writeHidden(wrap, adValue);
        updateHint(wrap, adValue);
    }

    function loadIntoVisible(wrap, adValue) {
        const bs = adDatetimeLocalToBs(adValue);
        const bsInput = wrap.querySelector(".nepali-bs-date");
        const timeInput = wrap.querySelector(".nepali-bs-time");
        const adInput = wrap.querySelector(".nepali-ad-datetime");
        if (bsInput && bs.bs) {
            bsInput.value = bs.bs;
        }
        if (timeInput && bs.time) {
            timeInput.value = bs.time;
        }
        if (adInput) {
            adInput.value = adValue || "";
        }
        updateHint(wrap, adValue);
    }

    function initWrap(wrap) {
        const hiddenId = wrap.dataset.hidden;
        const hidden = document.getElementById(hiddenId);
        if (!hidden) {
            return;
        }

        setCalMode(wrap, wrap.dataset.defaultCal || "bs");
        loadIntoVisible(wrap, hidden.value);
        syncFromVisible(wrap);

        wrap.querySelectorAll(".nepali-bs-date, .nepali-bs-time, .nepali-ad-datetime").forEach(function (el) {
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
                const adValue = readHidden(wrap);
                setCalMode(wrap, btn.dataset.cal);
                loadIntoVisible(wrap, adValue);
                syncFromVisible(wrap);
            });
        });

        const bsInput = wrap.querySelector(".nepali-bs-date");
        if (window.NepaliDatePicker && bsInput && bsInput.id) {
            new NepaliDatePicker("#" + bsInput.id, {
                format: "YYYY-MM-DD",
                locale: "np",
            });
        }
    }

    const api = {
        initAll: function (selector) {
            document.querySelectorAll(selector || ".nepali-datetime-wrap").forEach(initWrap);
        },
        syncAll: function () {
            document.querySelectorAll(".nepali-datetime-wrap").forEach(syncFromVisible);
        },
        setToday: function (hiddenId) {
            const wrap = document.querySelector('.nepali-datetime-wrap[data-hidden="' + hiddenId + '"]');
            if (!wrap) {
                return;
            }
            const now = new Date();
            const adValue = formatAdDatetimeLocal({
                year: now.getFullYear(),
                month: now.getMonth() + 1,
                day: now.getDate(),
                hours: now.getHours(),
                minutes: now.getMinutes(),
            });
            writeHidden(wrap, adValue);
            loadIntoVisible(wrap, adValue);
            syncFromVisible(wrap);
        },
    };

    window.ImsNepaliDatetime = api;
})(window);
