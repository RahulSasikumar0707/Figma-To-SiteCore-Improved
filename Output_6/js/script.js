(function () {
  'use strict';

  /* Sticky header: add a soft shadow once the page scrolls */
  var header = document.getElementById('eds-header');
  if (header) {
    var onScroll = function () {
      header.classList.toggle('is-scrolled', window.scrollY > 4);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* Placeholder links should not jump the page */
  document.querySelectorAll('a[href="#"]').forEach(function (link) {
    link.addEventListener('click', function (e) { e.preventDefault(); });
  });

  /* Demo forms (search, message, contact) — prevent navigation */
  document.querySelectorAll('.topbar-search, .amz-footer form').forEach(function (form) {
    form.addEventListener('submit', function (e) { e.preventDefault(); });
  });

  /* Deals carousel is driven entirely by Bootstrap via data-bs-target /
     data-bs-slide attributes on the prev/next controls — no custom JS. */
})();
