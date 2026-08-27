(function () {
  'use strict';

  // Header "Company" dropdown caret toggle – class-based only, no inline styles.
  var dropdowns = document.querySelectorAll('.nav-dropdown');

  dropdowns.forEach(function (item) {
    item.addEventListener('click', function (event) {
      event.preventDefault();
      var isOpen = item.classList.toggle('is-open');
      item.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
  });

  // Close open dropdowns when clicking elsewhere.
  document.addEventListener('click', function (event) {
    dropdowns.forEach(function (item) {
      if (!item.contains(event.target)) {
        item.classList.remove('is-open');
        item.setAttribute('aria-expanded', 'false');
      }
    });
  });
})();
