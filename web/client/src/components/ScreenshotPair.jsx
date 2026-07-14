import React from 'react';
import { imageUrl } from '../api.js';

export default function ScreenshotPair({ sessionId, figma, sitecore }) {
  return (
    <section className="shots">
      <figure>
        <figcaption>
          Figma — {figma.name} ({figma.width}×{figma.height})
        </figcaption>
        <div className="shot-frame">
          <img src={imageUrl(sessionId, 'figma')} alt="Figma design" loading="lazy" />
        </div>
      </figure>
      <figure>
        <figcaption>Sitecore — {sitecore.itemPath.split('/').pop()}</figcaption>
        <div className="shot-frame">
          <img src={imageUrl(sessionId, 'sitecore')} alt="Sitecore page render" loading="lazy" />
        </div>
      </figure>
    </section>
  );
}
