(function () {
  'use strict';

  // Sticky header: add subtle elevation once the page is scrolled
  var header = document.getElementById('eds-header');
  function onScroll() {
    if (!header) { return; }
    header.classList.toggle('is-scrolled', window.scrollY > 4);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // Navbar: manage active state and auto-close the mobile collapse on link click
  var collapseEl = document.getElementById('dhsNavbar');
  var navLinks = document.querySelectorAll('#dhsNavbar .nav-link');
  navLinks.forEach(function (link) {
    link.addEventListener('click', function () {
      navLinks.forEach(function (l) { l.classList.remove('active'); });
      link.classList.add('active');
      if (collapseEl && collapseEl.classList.contains('show') && window.bootstrap) {
        window.bootstrap.Collapse.getOrCreateInstance(collapseEl).hide();
      }
    });
  });
})();
