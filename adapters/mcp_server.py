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
    
    # State to persist last used project path
    state = {
        "last_project_path": None
    }

    def resolve_project_path(arguments: dict) -> str:
        """Infiere el project_path si no se provee."""
        path = arguments.get("project_path")
        if path:
            state["last_project_path"] = path
            return path
        
        if state["last_project_path"]:
            return state["last_project_path"]
        
        # Fallback to current working directory
        cwd = os.getcwd()
        sys.stderr.write(f"[WARN] No project_path provided. Falling back to CWD: {cwd}\n")
        state["last_project_path"] = cwd
        return cwd

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="ace_search_code",
                description="[v0.7.0] 💎 Hybrid search. project_path is OPTIONAL (infers from last call or CWD).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query"},
                        "project_path": {"type": "string", "description": "Absolute path (optional)"},
                        "file_pattern": {"type": "string", "description": "Optional glob pattern"}
                    },
                    "required": ["query"]
                }
            ),
            types.Tool(
                name="ace_index_status",
                description="Check index health. project_path is OPTIONAL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"}
                    }
                }
            ),
            types.Tool(
                name="ace_list_indexed",
                description="List indexed files. project_path is OPTIONAL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                        "pattern": {"type": "string"}
                    }
                }
            ),
            types.Tool(
                name="ace_index_project",
                description="Manual re-index. project_path is OPTIONAL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                        "force": {"type": "boolean"}
                    }
                }
            ),
            types.Tool(
                name="ace_boot_memory",
                description="[START OF SESSION] Load all memory. project_path is OPTIONAL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"}
                    }
                }
            ),
            types.Tool(
                name="ace_update_memory",
                description="Update memory. project_path is OPTIONAL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                        "memory_type": {"type": "string", "enum": ["context", "task", "lessons"]},
                        "content": {"type": "string"},
                        "append": {"type": "boolean", "default": False}
                    },
                    "required": ["memory_type", "content"]
                }
            )
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        sys.stderr.write(f"[DEBUG] call_tool invoked: {name} with {arguments}\n")
        
        try:
            if name == "ace_search_code":
                query = arguments.get("query")
                project_path = resolve_project_path(arguments)
                file_pattern = arguments.get("file_pattern")
                
                # Perform Search Logic directly
                results = indexer.query(project_path, query, file_pattern=file_pattern)
                
                text_output = []
                documents = results.get("documents", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]
                
                # Handle 0 Results with Stats
                if not documents:
                    meta = metadatas[0] if metadatas else {}
                    if meta.get("status") == "no_results":
                        text_output.append(f"❌ Found 0 matches for: '{query}'")
                        text_output.append(f"📊 Path: {project_path}")
                        text_output.append(f"📊 Project Status: {meta.get('indexed_files')} indexed files")
                        return [types.TextContent(type="text", text="\n".join(text_output))]

                text_output.append(f"Found {len(documents)} matching files for: {project_path}\n")
                
                for doc, meta in zip(documents, metadatas):
                    path = meta.get('path', 'unknown')
                    is_boosted = meta.get('boosted', False)
                    text_output.append(f"--- File: {path} {' [PRIORITY MATCH]' if is_boosted else ''} ---")
                    text_output.append(doc[:3000] if is_boosted else doc[:1500])
                    text_output.append("\n" + "-"*20 + "\n")
                
                return [types.TextContent(type="text", text="\n".join(text_output))]

            elif name == "ace_index_status":
                project_path = resolve_project_path(arguments)
                status = indexer.get_index_status(project_path)
                
                if status["status"] == "error":
                    return [types.TextContent(type="text", text=status["message"])]
                
                import datetime
                dt = datetime.datetime.fromtimestamp(status["last_update"]).strftime('%Y-%m-%d %H:%M:%S')
                output = [
                    f"📊 Index Status: {project_path}",
                    f"• Indexed files: {status['indexed_files_count']}",
                    f"• Last updated: {dt}"
                ]
                return [types.TextContent(type="text", text="\n".join(output))]

            elif name == "ace_list_indexed":
                project_path = resolve_project_path(arguments)
                pattern = arguments.get("pattern")
                files = indexer.list_indexed_files(project_path, pattern)
                file_list = "\n".join(files[:50])
                return [types.TextContent(type="text", text=f"Indexed files ({len(files)}):\n{file_list}")]

            elif name == "ace_index_project":
                project_path = resolve_project_path(arguments)
                force = arguments.get("force", False)
                stats = indexer.index_project(project_path, force=force)
                return [types.TextContent(type="text", text=f"Project Indexed Successfully.\nStats: {stats}")]

            elif name == "ace_boot_memory":
                from core.memory import MemoryManager
                project_path = resolve_project_path(arguments)
                manager = MemoryManager(project_path)
                content = manager.read("all")
                return [types.TextContent(type="text", text=content)]

            elif name == "ace_update_memory":
                from core.memory import MemoryManager
                project_path = resolve_project_path(arguments)
                memory_type = arguments.get("memory_type")
                content = arguments.get("content")
                append = arguments.get("append", False)
                manager = MemoryManager(project_path)
                result = manager.write(memory_type, content, append)
                return [types.TextContent(type="text", text=result)]
                
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return [types.TextContent(type="text", text=f"Error executing tool {name}: {str(e)}")]
    
    return app
