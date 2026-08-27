from figma_to_sitecore.figma.mcp import FigmaMcpClient, is_figma_remote_url


def test_remote_figma_mcp_url_is_detected() -> None:
    assert is_figma_remote_url("https://mcp.figma.com/mcp")
    assert not is_figma_remote_url("http://127.0.0.1:3845/mcp")


async def test_remote_figma_mcp_is_skipped_without_network() -> None:
    assert await FigmaMcpClient.try_connect("https://mcp.figma.com/mcp") is None
