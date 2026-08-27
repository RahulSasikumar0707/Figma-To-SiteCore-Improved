/**
 * Livdelzi Landing Page — behaviour layer.
 * All appearance is driven by classes in css/styles.css.
 * Bootstrap's collapse plugin manages the .collapsed class on accordion
 * toggles; the chevron rotation is handled purely in CSS.
 */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    document.body.classList.add('js-ready');

    // Keep aria-expanded in sync as a safety net for the accordion toggles
    // (Bootstrap already does this; this is a hook for GTM-style tracking).
    var collapses = document.querySelectorAll('.accordion-collapse');
    collapses.forEach(function (panel) {
      panel.addEventListener('shown.bs.collapse', function () {
        var toggle = document.querySelector('[data-bs-target="#' + panel.id + '"]');
        if (toggle) {
          toggle.setAttribute('aria-expanded', 'true');
        }
      });
      panel.addEventListener('hidden.bs.collapse', function () {
        var toggle = document.querySelector('[data-bs-target="#' + panel.id + '"]');
        if (toggle) {
          toggle.setAttribute('aria-expanded', 'false');
        }
      });
    });
  });
})();
