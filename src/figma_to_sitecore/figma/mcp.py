from __future__ import annotations

import base64
import json
import re
from contextlib import AsyncExitStack
from typing import Any
from urllib.parse import urlparse

import anyio

from figma_to_sitecore.utils.logging import log


class FigmaMcpClient:
    """Best-effort client for Figma Desktop's local Dev Mode MCP server."""

    def __init__(self, session: Any, tools: list[Any], stack: AsyncExitStack) -> None:
        self._session = session
        self._tools = tools
        self._stack = stack

    @classmethod
    async def try_connect(cls, url: str, timeout_seconds: float = 4) -> FigmaMcpClient | None:
        if is_figma_remote_url(url):
            log.warning(
                "The hosted Figma MCP endpoint requires an OAuth-enabled supported MCP host; "
                "the standalone converter will use REST instead"
            )
            return None
        stack = AsyncExitStack()
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            # Enter and exit the transport's AnyIO cancel scope in this task.
            # asyncio.wait_for creates another task and can corrupt MCP cleanup
            # when initialization fails or times out.
            streams = await stack.enter_async_context(streamable_http_client(url))
            read_stream, write_stream = streams[:2]
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            with anyio.fail_after(timeout_seconds):
                await session.initialize()
                result = await session.list_tools()
            tools = list(result.tools)
            log.info("Figma MCP connected (%s)", ", ".join(tool.name for tool in tools))
            return cls(session, tools, stack)
        except Exception as exc:
            try:
                await stack.aclose()
            except Exception as close_error:
                log.debug("Figma MCP cleanup also failed: %s", close_error)
            log.warning("Figma MCP unavailable at %s (%s); using REST only", url, exc)
            return None

    def _find_tool(self, patterns: list[str]) -> Any | None:
        for pattern in patterns:
            match = next((tool for tool in self._tools if re.search(pattern, tool.name, re.I)), None)
            if match:
                return match
        return None

    async def _call(self, tool: Any, node_id: str, extra: dict[str, Any] | None = None) -> Any | None:
        for key in ("nodeId", "node_id", "node-id"):
            arguments = {key: node_id, **(extra or {})}
            try:
                result = await self._session.call_tool(tool.name, arguments=arguments)
                if not getattr(result, "isError", False):
                    return result
            except Exception as exc:
                log.warning("MCP %s rejected %s (%s)", tool.name, key, exc)
        return None

    @staticmethod
    def _text(result: Any | None) -> str | None:
        parts = [item.text for item in getattr(result, "content", []) if getattr(item, "type", None) == "text"]
        return "\n".join(parts) if parts else None

    async def get_design_context(self, node_id: str) -> str | None:
        tool = self._find_tool([r"design_context", r"^get_code$", r"get_code"])
        if not tool:
            return None
        result = await self._call(
            tool,
            node_id,
            {"clientFrameworks": "html", "clientLanguages": "html,css,javascript"},
        )
        return self._text(result)

    async def get_variable_definitions(self, node_id: str) -> Any | None:
        tool = self._find_tool([r"variable"])
        if not tool:
            return None
        text = self._text(await self._call(tool, node_id))
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    async def get_screenshot(self, node_id: str) -> bytes | None:
        tool = self._find_tool([r"screenshot", r"^get_image$"])
        if not tool:
            return None
        result = await self._call(tool, node_id)
        image = next(
            (item for item in getattr(result, "content", []) if getattr(item, "type", None) == "image"),
            None,
        )
        return base64.b64decode(image.data) if image and getattr(image, "data", None) else None

    async def close(self) -> None:
        await self._stack.aclose()


def is_figma_remote_url(url: str) -> bool:
    """Return whether ``url`` is Figma's OAuth-protected hosted MCP endpoint."""
    return (urlparse(url).hostname or "").lower() == "mcp.figma.com"
