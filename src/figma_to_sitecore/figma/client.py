from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

import httpx


class FigmaApiError(RuntimeError):
    """Raised when Figma returns an unsuccessful response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FigmaRestClient:
    API_BASE = "https://api.figma.com"

    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._client = client or httpx.AsyncClient(follow_redirects=True, timeout=60)
        self._owns_client = client is None

    async def __aenter__(self) -> FigmaRestClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        clean_params = {key: value for key, value in (params or {}).items() if value not in (None, "")}
        response = await self._client.get(
            f"{self.API_BASE}{path}",
            params=clean_params,
            headers={"X-Figma-Token": self._token},
        )
        if response.is_error:
            detail = response.text[:300]
            try:
                body = response.json()
                if isinstance(body, dict):
                    detail = str(body.get("err") or body.get("message") or detail)
            except ValueError:
                pass
            normalized_detail = detail.lower()
            if response.status_code in {401, 403} and "token expired" in normalized_detail:
                message = (
                    "FIGMA_TOKEN has expired. In Figma, open Settings → Security → Personal access tokens, "
                    "generate a new token with the file_content:read scope, then replace FIGMA_TOKEN in .env."
                )
            elif response.status_code in {401, 403}:
                message = (
                    f"Figma denied REST access ({response.status_code}: {detail}). Check that FIGMA_TOKEN is "
                    "valid, includes file_content:read, and belongs to a user who can access this file."
                )
            else:
                message = f"Figma REST {path} returned {response.status_code}: {detail}"
            raise FigmaApiError(message, status_code=response.status_code)
        return response.json()

    async def get_nodes(self, file_key: str, ids: str | Iterable[str]) -> dict[str, Any]:
        node_ids = [ids] if isinstance(ids, str) else list(ids)
        data = await self._get(
            f"/v1/files/{quote(file_key, safe='')}/nodes",
            {"ids": ",".join(node_ids), "geometry": "paths"},
        )
        return data.get("nodes", {})

    async def render_images(
        self,
        file_key: str,
        ids: str | Iterable[str],
        *,
        image_format: str = "png",
        scale: float = 2,
    ) -> dict[str, str | None]:
        node_ids = [ids] if isinstance(ids, str) else list(ids)
        images: dict[str, str | None] = {}
        for offset in range(0, len(node_ids), 50):
            batch = node_ids[offset : offset + 50]
            params: dict[str, Any] = {"ids": ",".join(batch), "format": image_format}
            if image_format in {"png", "jpg"}:
                params["scale"] = scale
            elif image_format == "svg":
                params.update(svg_include_id="false", svg_simplify_stroke="true")
            data = await self._get(f"/v1/images/{quote(file_key, safe='')}", params)
            images.update(data.get("images") or {})
        return images

    async def get_image_fills(self, file_key: str) -> dict[str, str]:
        data = await self._get(f"/v1/files/{quote(file_key, safe='')}/images")
        return data.get("meta", {}).get("images", {})

    async def download(self, url: str) -> bytes:
        response = await self._client.get(url)
        if response.is_error:
            raise FigmaApiError(
                f"Download failed {response.status_code}: {url[:120]}",
                status_code=response.status_code,
            )
        return response.content
