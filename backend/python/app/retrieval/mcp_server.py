import asyncio
import json
import logging

from fastapi import HTTPException
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from .contracts import catalog
from .routes import execute


logger = logging.getLogger("argus.mcp")
server = Server("argus-research")
slots = asyncio.Semaphore(2)


@server.list_tools()
async def list_tools():
    return [Tool(name=item["name"], description=item["description"], inputSchema=item["parameters"], annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)) for item in catalog()]


@server.call_tool()
async def call_tool(name, arguments):
    try:
        async with slots:
            result = await asyncio.to_thread(execute, name, arguments)
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))], structuredContent=result)
    except HTTPException as error:
        return CallToolResult(content=[TextContent(type="text", text=json.dumps({"error": error.detail}, ensure_ascii=False))], isError=True)
    except Exception:
        logger.exception("MCP retrieval failed: %s", name)
        return CallToolResult(content=[TextContent(type="text", text="The retrieval service is unavailable. No result was inferred.")], isError=True)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, InitializationOptions(server_name="argus-research", server_version="0.1.0", capabilities=server.get_capabilities(notification_options=NotificationOptions(), experimental_capabilities={}), instructions="Published research sources only. Tools use fixed bounded queries, not model-written Cypher. Graph paths and structural ranks are not scientific conclusions. Long-term findings memory and recall are disabled."))


if __name__ == "__main__":
    asyncio.run(main())
