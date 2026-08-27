/* Medicust — behavior layer (Bootstrap handles collapse/interactive widgets) */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var header = document.getElementById('eds-header');

    /* Sticky header shadow on scroll */
    var onScroll = function () {
      if (!header) { return; }
      header.classList.toggle('is-scrolled', window.scrollY > 10);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    /* Close the mobile nav when a nav link is clicked */
    var navCollapse = document.getElementById('primaryNavigation');
    if (navCollapse) {
      navCollapse.querySelectorAll('.nav-link').forEach(function (link) {
        link.addEventListener('click', function () {
          if (window.getComputedStyle(document.querySelector('.navbar-toggler')).display !== 'none') {
            var instance = bootstrap.Collapse.getInstance(navCollapse);
            if (instance) { instance.hide(); }
          }
        });
      });
    }
  });
})();
