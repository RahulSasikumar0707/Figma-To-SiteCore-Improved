# HTML Comparison Report

- **Live URL:** https://dxcmpt6.gilead.com/about-vanddmyo
- **Generated file:** \\z1xa7prdhomes.file.core.windows.net\prdhomes\Homes\ugg\Documents\Figma-To-SiteCore-Improved\Output_2\index.html
- **Model:** claude-opus-4-8
- **Generated at:** 2026-07-14T09:46:45.701Z
- **Estimated content match:** 74%

## Summary

The generated page reproduces the main content structure and copy of the About VANDDMYO page fairly well — hero, intro split, three how-it-works cards, eligibility flip cards, ask-about CTA, dual CTA panels, ISI, and footer are all present in the correct order with mostly accurate text. However several notable gaps exist: the BCMA accordion body content is entirely empty (missing two list items), the eligibility flip-card BACK content (all four cards' details) is missing, the ISI tray full detail/offcanvas content is reduced to a truncated placeholder, header nav lacks the Prescribing/Important Facts/HCP link destinations and mobile menu, and there is an 'FPO' placeholder in the ISI. Page title and meta/SEO tags are also simplified.

## Differences (12)

### 1. [CRITICAL] BCMA accordion — missing

- **Live:** <ul><li>The special "grabbers" on [VANDDMYO] are <strong>designed to be small and stable</strong>...</li><li>The <strong>trained cells are engineered for a “quick release.”</strong>...</li></ul>
- **Generated:** <div class="eds-accordion-body"></div> (empty)
- **Fix:** Populate the accordion body with the two bullet points describing the small/stable grabbers and quick-release engineering.

### 2. [CRITICAL] Eligibility flip cards (back content) — missing

- **Live:** Each flip card has back content, e.g. 'Living with multiple myeloma and having had at least 3 kinds of treatment not work...', 'Tried 3 or more different types of treatments... Immunomodulators / Proteasome inhibitors / Anti-CD38 antibodies', 'Have multiple myeloma that is standard or high risk', 'Age 18 years or older', plus a 'Reset' CTA.
- **Generated:** Flip cards only render the front (title + 'Find out more'); no back-face content, list items, or Reset CTA.
- **Fix:** Add the card-back content and Reset controls for all four eligibility flip cards to preserve the interactive detail.

### 3. [MAJOR] ISI tray (offcanvas detail) — truncated

- **Live:** Full ISI offcanvas with tabs (Approved Uses / Safety Information), detailed 'How will I receive', 'What should I avoid', side effects lists, CRS paragraph, FDA MedWatch link, and Important Facts link.
- **Generated:** Only a short two-column summary and a 'Read' button; no offcanvas detail content or tabs.
- **Fix:** Include the full ISI offcanvas markup with detailed safety information, tabs, and footer navigation as on the live page.

### 4. [MAJOR] ISI section — placeholder

- **Live:** n/a
- **Generated:** <span class="isi-fpo" aria-hidden="true">FPO</span>
- **Fix:** Remove the 'FPO' placeholder from the ISI floating tray.

### 5. [MAJOR] Header secondary navigation links — link

- **Live:** Prescribing Information -> https://www.gilead.com/, Important Facts -> /edsredesign, Visit HCP Site -> https://www.gilead.com/ (with external icon and target=_blank).
- **Generated:** All three links point to '#' with a generic icon-button.svg.
- **Fix:** Restore the correct destinations, external-link behavior, and icons for the secondary nav links.

### 6. [MINOR] Header primary navigation links — link

- **Live:** Nav items link to /about-vanddmyo, /results-and-side-effects, /starting-vanddmyo, /voices-of-vanddmyo, /support-and-resources, /find-a-treatment-center.
- **Generated:** All nav links point to '#'.
- **Fix:** Set the correct href targets for each main navigation item.

### 7. [MINOR] Sign up / CTAs destinations — link

- **Live:** Sign up -> /sign-up; Doctor discussion guide -> /support-and-resources#downloadable-resources-section; Stay informed -> /sign-up; See the lasting results -> /results-and-side-effects.
- **Generated:** All these CTAs point to '#'.
- **Fix:** Point CTAs at their live destinations.

### 8. [MINOR] Document head / SEO — mismatch

- **Live:** <title>What is VANDDMYO®? | A CAR T-Cell Therapy for Myeloma</title> plus canonical, og:, twitter:, and meta description tags.
- **Generated:** <title>About [VANDDMYO]</title> with no canonical/og/twitter/meta description tags.
- **Fix:** Add the proper page title and SEO/social meta tags matching the live page.

### 9. [MINOR] Header logo — image

- **Live:** Single SVG logo image (logos.svg) with alt 'VANDDMYO (vandecabtagene autoleucel) logo'.
- **Generated:** Logo reconstructed from ~30 absolutely positioned vector SVG fragments.
- **Fix:** Replace the fragmented SVG assembly with the single logos.svg image for maintainability and correct alt text.

### 10. [MINOR] Header mobile menu / hamburger nav items — missing

- **Live:** Mobile hamburger menu includes duplicate Prescribing Information, Important Facts, and Visit HCP Site links.
- **Generated:** Mobile toggle exists but the mobile-only external link list is absent.
- **Fix:** Add the mobile-hm-links list for parity on small screens.

### 11. [MINOR] Footer social icons order — order

- **Live:** Order: Instagram, Facebook, YouTube.
- **Generated:** Order: Facebook, Instagram, YouTube.
- **Fix:** Reorder footer social icons to Instagram, Facebook, YouTube to match live.

### 12. [MINOR] How it works card 1 body — mismatch

- **Live:** 'Your newly trained T cells have special "grabbers"...' with 'newly trained T cells' emphasized as part of a larger bold span.
- **Generated:** Emphasis boundaries differ slightly (e.g., <strong>newly trained T cells</strong> separated), otherwise text matches.
- **Fix:** Minor; align bold emphasis spans with live copy if exact styling matters.
