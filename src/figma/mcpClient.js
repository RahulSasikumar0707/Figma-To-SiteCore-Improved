/**
 * Client for the Figma desktop app's local Dev Mode MCP server
 * (default http://127.0.0.1:3845/mcp).
 *
 * Tool names have shifted between Figma releases (get_code -> get_design_context,
 * get_image -> get_screenshot, ...), so tools are discovered by pattern instead
 * of hardcoded names. Every method degrades to null so the pipeline can fall
 * back to the REST source.
 */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { log } from '../utils/log.js';

function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_, rej) => setTimeout(() => rej(new Error(`${label} timed out after ${ms}ms`)), ms)),
  ]);
}

export class FigmaMcp {
  constructor(client, tools) {
    this.client = client;
    this.tools = tools;
  }

  /** Returns a connected FigmaMcp, or null if the local server is not running. */
  static async tryConnect(url, timeoutMs = 4000) {
    try {
      const client = new Client({ name: 'figma-eds-converter', version: '1.0.0' });
      const transport = new StreamableHTTPClientTransport(new URL(url));
      await withTimeout(client.connect(transport), timeoutMs, 'MCP connect');
      const { tools } = await withTimeout(client.listTools(), timeoutMs, 'MCP listTools');
      log.ok(`Figma MCP server connected (${tools.length} tools: ${tools.map((t) => t.name).join(', ')})`);
      return new FigmaMcp(client, tools);
    } catch (err) {
      log.warn(`Figma MCP server not reachable at ${url} (${err.message}). Falling back to REST API.`);
      return null;
    }
  }

  #findTool(patterns) {
    for (const p of patterns) {
      const tool = this.tools.find((t) => p.test(t.name));
      if (tool) return tool;
    }
    return null;
  }

  async #call(tool, nodeId, extraArgs = {}) {
    // Different server versions accept nodeId / node_id / node-id. Every
    // attempt carries the node id: an id-less call would make the server use
    // the CURRENT SELECTION in the Figma desktop app — silently wrong data.
    const attempts = [
      { nodeId, ...extraArgs },
      { node_id: nodeId, ...extraArgs },
      { 'node-id': nodeId, ...extraArgs },
    ];
    for (const args of attempts) {
      try {
        const res = await this.client.callTool({ name: tool.name, arguments: args });
        if (!res.isError) return res;
      } catch (err) {
        log.warn(`MCP ${tool.name} rejected argument shape ${Object.keys(args).join(',')}: ${err.message}`);
      }
    }
    return null;
  }

  static #text(res) {
    if (!res?.content) return null;
    const parts = res.content.filter((c) => c.type === 'text').map((c) => c.text);
    return parts.length ? parts.join('\n') : null;
  }

  /** Figma's own code/markup representation of the node — strong grounding for the LLM. */
  async getDesignContext(nodeId) {
    const tool = this.#findTool([/design_context/i, /^get_code$/i, /get_code/i]);
    if (!tool) return null;
    const res = await this.#call(tool, nodeId, { clientFrameworks: 'html', clientLanguages: 'html,css,javascript' });
    return FigmaMcp.#text(res);
  }

  /** Variable/token definitions used by the node (real design tokens). */
  async getVariableDefs(nodeId) {
    const tool = this.#findTool([/variable/i]);
    if (!tool) return null;
    const res = await this.#call(tool, nodeId);
    const text = FigmaMcp.#text(res);
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch {
      return text; // some versions return "name: value" lines
    }
  }

  /** Screenshot of the node as rendered in Figma (base64 png), if the server offers it. */
  async getScreenshot(nodeId) {
    const tool = this.#findTool([/screenshot/i, /^get_image$/i]);
    if (!tool) return null;
    const res = await this.#call(tool, nodeId);
    const img = res?.content?.find((c) => c.type === 'image');
    if (img?.data) return Buffer.from(img.data, 'base64');
    return null;
  }

  async close() {
    try {
      await this.client.close();
    } catch {
      /* ignore */
    }
  }
}
