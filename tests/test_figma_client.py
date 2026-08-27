import httpx
import pytest

from figma_to_sitecore.figma.client import FigmaApiError, FigmaRestClient


async def test_expired_figma_token_has_actionable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"status": 403, "err": "Token expired"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        rest = FigmaRestClient("expired", http_client)
        with pytest.raises(FigmaApiError, match="FIGMA_TOKEN has expired") as captured:
            await rest.get_nodes("file", "1:2")

    assert captured.value.status_code == 403


async def test_figma_permission_error_mentions_scope_and_file_access() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"err": "Invalid scope"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        rest = FigmaRestClient("wrong-scope", http_client)
        with pytest.raises(FigmaApiError, match="file_content:read"):
            await rest.get_nodes("file", "1:2")
