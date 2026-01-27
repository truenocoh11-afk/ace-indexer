import asyncio
import httpx
import sys
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
import mcp.types as types

ACE_API_URL = "http://127.0.0.1:8000"

async def _query_ace(endpoint: str, payload: dict, project_path: str):
    try:
        headers = {"X-Project-Path": project_path if project_path else ""}
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{ACE_API_URL}{endpoint}", json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return {"error": str(e)}

# Expose the server instance creation
def create_mcp_server():
    app = Server("Antigravity Context Engine (ACE)")

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="ace_search_code",
                description="Search the codebase using Hybrid RAG (Keywords + Semantic). Returns relevant code skeletons.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query (e.g. 'how does login work')"},
                        "project_path": {"type": "string", "description": "Absolute path to the project root"}
                    },
                    "required": ["query", "project_path"]
                }
            ),
            types.Tool(
                name="ace_index_project",
                description="Trigger a manual re-index of the project.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                        "force": {"type": "boolean"}
                    },
                    "required": ["project_path"]
                }
            )
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        print(f"[DEBUG] call_tool invoked: {name} with {arguments}")
        if name == "ace_search_code":
            query = arguments.get("query")
            project_path = arguments.get("project_path")
            
            print(f"[DEBUG] Querying ACE API for: {query}")
            result = await _query_ace("/v1/context/query", {"query": query}, project_path)
            print(f"[DEBUG] Query finished. Result size: {len(result.get('results', [])) if 'results' in result else 0}")
            
            if "error" in result:
                return [types.TextContent(type="text", text=f"Error: {result['error']}")]
            
            text_output = []
            text_output.append(f"Found {len(result.get('results', []))} matches context for: {project_path}\n")
            
            for res in result.get("results", []):
                text_output.append(f"--- File: {res['file_path']} ({res['type']}) ---")
                text_output.append(res['content'])
                text_output.append("\n" + "-"*20 + "\n")
            
            return [types.TextContent(type="text", text="\n".join(text_output))]

        elif name == "ace_index_project":
            project_path = arguments.get("project_path")
            force = arguments.get("force", False)
            result = await _query_ace("/v1/context/index", {"project_path": project_path, "force": force}, project_path)
            
            msg = str(result)
            msg += "\n\n(Note: Index stored in .ace/ folder. A .gitignore file was automatically created inside it to prevent committing the index.)"
            return [types.TextContent(type="text", text=msg)]
            
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
    
    return app


