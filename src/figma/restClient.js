/**
 * Figma REST API client.
 * Used as the primary structured source for the node tree, asset export and
 * the reference screenshot. Works headless (no Figma desktop app needed).
 */
const API = 'https://api.figma.com';

export class FigmaRest {
  constructor(token) {
    this.token = token;
  }

  async #get(pathname, params = {}) {
    const url = new URL(API + pathname);
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    }
    const res = await fetch(url, { headers: { 'X-Figma-Token': this.token } });
    if (!res.ok) {
      const body = await res.text().catch(() => '');
      throw new Error(`Figma REST ${pathname} -> ${res.status}: ${body.slice(0, 300)}`);
    }
    return res.json();
  }

  /** Full subtree of one or more nodes (geometry included so vectors are detectable). */
  async getNodes(fileKey, ids) {
    const data = await this.#get(`/v1/files/${fileKey}/nodes`, {
      ids: [].concat(ids).join(','),
      geometry: 'paths',
    });
    return data.nodes; // { "<id>": { document, components, styles, ... } }
  }

  /**
   * Server-side render of nodes -> temporary URLs.
   * format: png | svg | jpg ; scale only applies to bitmap formats.
   */
  async renderImages(fileKey, ids, { format = 'png', scale = 2 } = {}) {
    const all = {};
    const list = [].concat(ids);
    for (let i = 0; i < list.length; i += 50) {
      const batch = list.slice(i, i + 50);
      const params = { ids: batch.join(','), format };
      if (format === 'png' || format === 'jpg') params.scale = scale;
      if (format === 'svg') {
        params.svg_include_id = 'false';
        params.svg_simplify_stroke = 'true';
      }
      const data = await this.#get(`/v1/images/${fileKey}`, params);
      Object.assign(all, data.images || {});
    }
    return all; // { "<nodeId>": "https://..." | null }
  }

  /** Original bitmap fills of the file: { imageRef: url }. Keeps original quality. */
  async getImageFills(fileKey) {
    const data = await this.#get(`/v1/files/${fileKey}/images`);
    return data?.meta?.images || {};
  }

  /** Published/local styles metadata for the file (used for token naming). */
  async getFileStyles(fileKey) {
    try {
      const data = await this.#get(`/v1/files/${fileKey}/styles`);
      return data?.meta?.styles || [];
    } catch {
      return [];
    }
  }

  async download(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Download failed ${res.status}: ${url.slice(0, 120)}`);
    return Buffer.from(await res.arrayBuffer());
  }
}
