// main.js — students will add JavaScript here as features are built

// Any form with a data-confirm attribute asks before submitting (e.g. delete).
// Uses the themed <dialog id="confirm-dialog"> when the page provides one and
// the browser supports it; otherwise falls back to window.confirm.
(function () {
    var pendingForm = null;
    var opener = null;

    function getDialog() {
        var found = document.getElementById("confirm-dialog");
        return found && typeof found.showModal === "function" ? found : null;
    }

    document.addEventListener("submit", function (event) {
        var form = event.target;
        var message = form.getAttribute && form.getAttribute("data-confirm");
        if (!message) {
            return;
        }
        var dialog = getDialog();
        if (!dialog) {
            if (!window.confirm(message)) {
                event.preventDefault();
            }
            return;
        }
        event.preventDefault();
        if (dialog.open) {
            return;
        }
        pendingForm = form;
        opener = document.activeElement;
        dialog.querySelector("#confirm-dialog-title").textContent = message;
        var detail = dialog.querySelector("#confirm-dialog-detail");
        var text = form.getAttribute("data-confirm-detail") || "";
        detail.textContent = text;
        detail.hidden = !text;
        dialog.showModal();
        dialog.querySelector("#confirm-dialog-cancel").focus();
    });

    var dialog = getDialog();
    if (!dialog) {
        return;
    }

    dialog.querySelector("#confirm-dialog-cancel").addEventListener("click", function () {
        dialog.close("cancel");
    });

    dialog.querySelector("#confirm-dialog-ok").addEventListener("click", function () {
        var form = pendingForm;
        pendingForm = null;
        dialog.close("confirm");
        if (form) {
            form.submit(); // does not fire a submit event, so no re-prompt loop
        }
    });

    // The dialog has no padding, so a click whose target is the dialog itself
    // landed on the ::backdrop.
    dialog.addEventListener("click", function (event) {
        if (event.target === dialog) {
            dialog.close("cancel");
        }
    });

    // Fires for Esc, Cancel, backdrop and Confirm alike.
    dialog.addEventListener("close", function () {
        pendingForm = null;
        if (opener && document.contains(opener) && typeof opener.focus === "function") {
            opener.focus();
        }
        opener = null;
    });
})();

// Profile date filter: keep the From/To pickers consistent (From <= To, and
// neither later than today, which the server sends as the inputs' max).
// The server re-validates; this only gives immediate feedback.
(function () {
    var from = document.getElementById("profile-date-from");
    var to = document.getElementById("profile-date-to");
    if (!from || !to) {
        return;
    }
    var cap = to.getAttribute("max") || "";

    function sync() {
        to.min = from.value || "";
        // From can't pass To, and neither can pass today.
        from.max = to.value && (!cap || to.value < cap) ? to.value : cap;

        from.setCustomValidity(
            cap && from.value > cap ? "Dates cannot be in the future." : ""
        );
        var message = "";
        if (cap && to.value > cap) {
            message = "Dates cannot be in the future.";
        } else if (from.value && to.value && from.value > to.value) {
            message = "End date must be on or after the start date.";
        }
        to.setCustomValidity(message);
    }

    ["input", "change"].forEach(function (name) {
        from.addEventListener(name, sync);
        to.addEventListener(name, sync);
    });
    sync();
})();
