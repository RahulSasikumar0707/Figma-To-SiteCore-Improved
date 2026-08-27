/* Livdelzi Landing Page — behaviors.
   Accordions use native Bootstrap 5 collapse (data-bs-* attributes).
   Sticky header is CSS-driven (position: sticky); this file only adds
   light progressive enhancements. */

document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  // Toggle a state class on the sticky header while the page is scrolled,
  // so projects can hook extra styling (e.g. stronger shadow) if desired.
  var header = document.getElementById('eds-header');
  if (header) {
    var onScroll = function () {
      header.classList.toggle('is-scrolled', window.scrollY > 0);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // Smooth-scroll for same-page anchors (e.g. "Important Safety Information"),
  // compensating for the sticky header height.
  document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener('click', function (e) {
      var targetId = link.getAttribute('href');
      if (targetId && targetId.length > 1) {
        var target = document.querySelector(targetId);
        if (target) {
          e.preventDefault();
          var headerH = header ? header.offsetHeight : 0;
          var top = target.getBoundingClientRect().top + window.pageYOffset - headerH - 8;
          window.scrollTo({ top: top, behavior: 'smooth' });
        }
      }
    });
  });
});
