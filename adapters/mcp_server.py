import asyncio
import sys
import os
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
import mcp.types as types

# Direct Import of Core Logic (No HTTP)
from core.indexer import Indexer

# Expose the server instance creation
def create_mcp_server():
    app = Server("Antigravity Context Engine (ACE)")
    indexer = Indexer()

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="ace_search_code",
                description="[v0.2.0] Search the codebase using Hybrid RAG (Keywords + Semantic) with optional file filtering. Returns relevant code skeletons.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query (e.g. 'how does login work')"},
                        "project_path": {"type": "string", "description": "Absolute path to the project root"},
                        "file_pattern": {"type": "string", "description": "Optional glob pattern to filter files (e.g. '*.js', 'test_*.py')"}
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
        
        try:
            if name == "ace_search_code":
                query = arguments.get("query")
                project_path = arguments.get("project_path")
                file_pattern = arguments.get("file_pattern")
                
                print(f"[DEBUG] Executing direct search for: {query} in {project_path} (pattern: {file_pattern})")
                
                # Perform Search Logic directly
                results = indexer.query(project_path, query, file_pattern=file_pattern)
                
                text_output = []
                # Check chroma result structure (ids, metadatas, documents)
                documents = results.get("documents", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]
                
                text_output.append(f"Found {len(documents)} matches context for: {project_path}\n")
                
                MAX_LEN = 1500
                BOOSTED_MAX_LEN = 3000

                for doc, meta in zip(documents, metadatas):
                    path = meta.get('path', 'unknown')
                    is_boosted = meta.get('boosted', False)
                    limit = BOOSTED_MAX_LEN if is_boosted else MAX_LEN
                    
                    # Snippet Truncation Logic
                    if len(doc) > limit:
                        head = doc[:int(limit * 0.7)]
                        tail = doc[-int(limit * 0.2):]
                        display_doc = f"{head}\n\n... [TRUNCATED {len(doc) - limit} chars for clarity] ...\n\n{tail}"
                    else:
                        display_doc = doc

                    text_output.append(f"--- File: {path} {' [PRIORITY MATCH]' if is_boosted else ''} ---")
                    text_output.append(display_doc)
                    text_output.append("\n" + "-"*20 + "\n")
                
                return [types.TextContent(type="text", text="\n".join(text_output))]

            elif name == "ace_index_project":
                project_path = arguments.get("project_path")
                force = arguments.get("force", False)
                
                print(f"[DEBUG] Executing direct index for: {project_path}")
                if not os.path.exists(project_path):
                    return [types.TextContent(type="text", text=f"Error: Path {project_path} does not exist.")]

                # Run Indexer Synchronously (or offload to thread if needed, but Indexer is mostly I/O)
                # Since we are in an async function, strictly speaking we should run_in_executor
                # but for simplicity/reliability in this fix we call it directly.
                stats = indexer.index_project(project_path, force=force)
                
                msg = f"Project Indexed Successfully.\nStats: {stats}"
                msg += "\n\n(Note: Index stored in .ace/ folder inside the project.)"
                return [types.TextContent(type="text", text=msg)]
                
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return [types.TextContent(type="text", text=f"Error executing tool {name}: {str(e)}")]
    
    return app


