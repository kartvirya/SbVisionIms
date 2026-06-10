document.addEventListener("DOMContentLoaded", function () {
    function rowFor(el) {
        return el.closest("[data-brand-row]");
    }

    function enterEdit(row) {
        row.classList.add("vb-row-editing");
        row.querySelectorAll(".vb-view").forEach(function (el) {
            el.classList.add("d-none");
        });
        row.querySelectorAll(".vb-edit").forEach(function (el) {
            el.classList.remove("d-none");
        });
    }

    function leaveEdit(row) {
        row.classList.remove("vb-row-editing");
        row.querySelectorAll(".vb-view").forEach(function (el) {
            el.classList.remove("d-none");
        });
        row.querySelectorAll(".vb-edit").forEach(function (el) {
            el.classList.add("d-none");
        });
    }

    document.addEventListener("click", function (e) {
        const editBtn = e.target.closest(".vb-btn-edit");
        if (editBtn) {
            const row = rowFor(editBtn);
            if (row) {
                enterEdit(row);
            }
            return;
        }
        const cancelBtn = e.target.closest(".vb-btn-cancel");
        if (cancelBtn) {
            const row = rowFor(cancelBtn);
            if (row) {
                leaveEdit(row);
            }
        }
    });
});
