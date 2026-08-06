/**
 * Prevent mouse wheel from changing focused <input type="number"> values.
 * Stops accidental mis-input when scrolling product forms and other pages.
 */
(function () {
  function onWheel(event) {
    var target = event.target;
    if (target && target.matches && target.matches('input[type="number"]:focus')) {
      event.preventDefault();
    }
  }

  document.addEventListener('wheel', onWheel, { passive: false, capture: true });
})();
