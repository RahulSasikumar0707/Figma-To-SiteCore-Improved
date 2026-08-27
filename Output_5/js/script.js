(function () {
  'use strict';

  // Deals carousel arrows: the track is a scroll container at every width,
  // so the arrows always have something to act on. No inline styles are
  // written; scrolling only.
  var track = document.querySelector('.deals-track');
  var arrows = document.querySelectorAll('.deals-arrow');
  arrows.forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!track) { return; }
      var direction = btn.classList.contains('deals-arrow--next') ? 1 : -1;
      track.scrollBy({ left: direction * 340, behavior: 'smooth' });
    });
  });

  // Intl cards row behaves the same way if it overflows.
  var intlCards = document.querySelector('.intl-cards');
  if (intlCards) {
    intlCards.setAttribute('tabindex', '0');
    intlCards.setAttribute('aria-label', 'Featured collections');
  }

  // Prevent placeholder anchors from jumping the page.
  document.querySelectorAll('a[href="#"]').forEach(function (anchor) {
    anchor.addEventListener('click', function (event) {
      event.preventDefault();
    });
  });

  // Newsletter send: mark the subscribe block via class toggle only.
  var sendBtn = document.querySelector('.subscribe-send');
  if (sendBtn) {
    sendBtn.addEventListener('click', function () {
      var subscribe = sendBtn.closest('.subscribe');
      if (subscribe) {
        subscribe.classList.add('is-submitted');
      }
    });
  }
})();
