/**
 * B.S. date + time inputs synced to hidden A.D. datetime-local fields for Django forms.
 */
(function (window) {
    function pad(n) {
        return String(n).padStart(2, "0");
    }

    function getNepaliDateClass() {
        return window.NepaliDate && window.NepaliDate.default ? window.NepaliDate.default : null;
    }

    function adDatetimeLocalToBs(adValue) {
        const ND = getNepaliDateClass();
        if (!ND || !adValue) {
            return { bs: "", time: "12:00" };
        }
        const parts = adValue.split("T");
        const datePart = parts[0];
        const timePart = parts[1] || "12:00";
        const ymd = datePart.split("-").map(Number);
        const nd = ND.fromAD(new Date(ymd[0], ymd[1] - 1, ymd[2]));
        return { bs: nd.format("YYYY-MM-DD"), time: timePart.slice(0, 5) };
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
        return (
            js.getFullYear() +
            "-" +
            pad(js.getMonth() + 1) +
            "-" +
            pad(js.getDate()) +
            "T" +
            pad(hm[0] || 0) +
            ":" +
            pad(hm[1] || 0)
        );
    }

    function syncWrap(wrap) {
        const hiddenId = wrap.dataset.hidden;
        const hidden = document.getElementById(hiddenId);
        const bsInput = wrap.querySelector(".nepali-bs-date");
        const timeInput = wrap.querySelector(".nepali-bs-time");
        const hint = wrap.querySelector(".nepali-ad-hint");
        if (!hidden || !bsInput || !timeInput) {
            return;
        }
        hidden.value = bsAndTimeToAdDatetimeLocal(bsInput.value, timeInput.value);
        if (hint) {
            hint.textContent = hidden.value
                ? "A.D. " + hidden.value.replace("T", " ")
                : "";
        }
    }

    function initWrap(wrap) {
        const hiddenId = wrap.dataset.hidden;
        const hidden = document.getElementById(hiddenId);
        const bsInput = wrap.querySelector(".nepali-bs-date");
        const timeInput = wrap.querySelector(".nepali-bs-time");
        if (!hidden || !bsInput || !timeInput) {
            return;
        }

        const initial = adDatetimeLocalToBs(hidden.value);
        if (initial.bs) {
            bsInput.value = initial.bs;
        }
        if (initial.time) {
            timeInput.value = initial.time;
        }
        syncWrap(wrap);

        bsInput.addEventListener("change", function () {
            syncWrap(wrap);
        });
        timeInput.addEventListener("change", function () {
            syncWrap(wrap);
        });
        timeInput.addEventListener("input", function () {
            syncWrap(wrap);
        });

        if (window.NepaliDatePicker && bsInput.id) {
            new NepaliDatePicker("#" + bsInput.id, {
                format: "YYYY-MM-DD",
                locale: "np",
            });
            bsInput.addEventListener("input", function () {
                syncWrap(wrap);
            });
        }
    }

    const api = {
        initAll: function (selector) {
            document.querySelectorAll(selector || ".nepali-datetime-wrap").forEach(initWrap);
        },
        syncAll: function () {
            document.querySelectorAll(".nepali-datetime-wrap").forEach(syncWrap);
        },
        setToday: function (hiddenId) {
            const wrap = document.querySelector('.nepali-datetime-wrap[data-hidden="' + hiddenId + '"]');
            if (!wrap) {
                return;
            }
            const now = new Date();
            const hidden = document.getElementById(hiddenId);
            const adValue =
                now.getFullYear() +
                "-" +
                pad(now.getMonth() + 1) +
                "-" +
                pad(now.getDate()) +
                "T" +
                pad(now.getHours()) +
                ":" +
                pad(now.getMinutes());
            if (hidden) {
                hidden.value = adValue;
            }
            const initial = adDatetimeLocalToBs(adValue);
            const bsInput = wrap.querySelector(".nepali-bs-date");
            const timeInput = wrap.querySelector(".nepali-bs-time");
            if (bsInput) {
                bsInput.value = initial.bs;
            }
            if (timeInput) {
                timeInput.value = initial.time;
            }
            syncWrap(wrap);
        },
    };

    window.ImsNepaliDatetime = api;
})(window);
