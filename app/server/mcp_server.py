from typing import Any, Dict, List

from fastmcp import Client, FastMCP

from app.advanced_funcs.logging_client import logger

mcp = FastMCP("AgentToolsServer")
mcp_client = Client(mcp)


async def get_available_tools() -> List[Dict[str, Any]]:
    """Получает список доступных инструментов с MCP-сервера."""
    async with mcp_client:
        tools = await mcp_client.list_tools()
        tool_descriptions = []
        for tool in tools:
            desc = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": (
                    tool.inputSchema.model_dump() if tool.inputSchema else {}
                ),
                "tags": (
                    tool.meta.get("_fastmcp", {}).get("tags", []) if tool.meta else []
                ),
            }
            tool_descriptions.append(desc)
        return tool_descriptions


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Выполняет инструмент на MCP-сервере."""
    try:
        async with mcp_client:
            result = await mcp_client.call_tool(
                tool_name, arguments, raise_on_error=True
            )
            return {
                "success": True,
                "data": result.data,
                "raw": (
                    result.structured_content or str(result.content[0].text)
                    if result.content
                    else None
                ),
            }
    except Exception as e:
        logger.error(f"Ошибка выполнения инструмента {tool_name}: {e}")
        return {"success": False, "error": str(e), "data": None}


async def run_mcp_server():
    await mcp.run_async()
