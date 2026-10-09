"""Connect to both MCP servers (ours + the external one) via langchain-mcp-adapters."""
import json
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import settings


async def load_tools():
    """Return LangChain tools from all configured MCP servers."""
    client = MultiServerMCPClient(
        {
            "learner-intelligence": {"transport": "streamable_http", "url": settings.learner_mcp_url},
            # TODO: add the external documents server from mcp_servers.json
        }
    )
    return await client.get_tools()


def registry() -> dict:
    p = Path(__file__).resolve().parents[3] / "mcp_servers.json"
    return json.loads(p.read_text()) if p.exists() else {}
