// main.js — students will add JavaScript here as features are built

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
