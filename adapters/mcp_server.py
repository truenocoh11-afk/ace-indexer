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
                description="[v0.4.0] 🔥 RECOMMENDED. Smart hybrid search with re-ranking. Automatically detects if you are searching for code literals or concepts.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query (e.g. 'initialization of lastAgentStats')"},
                        "project_path": {"type": "string", "description": "Absolute path to the project root"},
                        "file_pattern": {"type": "string", "description": "Optional glob pattern (e.g. '*.js', 'test_*.py')"}
                    },
                    "required": ["query", "project_path"]
                }
            ),
            types.Tool(
                name="ace_index_status",
                description="Check if project index is healthy and detect missing files.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"}
                    },
                    "required": ["project_path"]
                }
            ),
            types.Tool(
                name="ace_list_indexed",
                description="List all files currently in the index (for debugging).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                        "pattern": {"type": "string", "description": "Optional pattern filter"}
                    },
                    "required": ["project_path"]
                }
            ),
            types.Tool(
                name="ace_index_project",
                description="Trigger a manual re-index. Use force=True to fix missing files.",
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
        import sys
        sys.stderr.write(f"[DEBUG] call_tool invoked: {name} with {arguments}\\n")
        
        try:
            if name == "ace_search_code":
                query = arguments.get("query")
                project_path = arguments.get("project_path")
                file_pattern = arguments.get("file_pattern")
                
                # Perform Search Logic directly
                results = indexer.query(project_path, query, file_pattern=file_pattern)
                
                text_output = []
                documents = results.get("documents", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]
                
                # [v0.2.1] Handle 0 Results with Stats
                if not documents:
                    meta = metadatas[0] if metadatas else {}
                    if meta.get("status") == "no_results":
                        text_output.append(f"❌ Found 0 matches for: '{query}'")
                        text_output.append(f"📊 Project Status: {meta.get('indexed_files')} indexed files (Pattern: '{meta.get('pattern')}')")
                        
                        missing = meta.get("missing_files", [])
                        if missing:
                            text_output.append("\n⚠️ POTENTIAL ISSUES DETECTED:")
                            text_output.append(f"Found {len(missing)} files on disk that are NOT in the index yet:")
                            for m in missing: text_output.append(f"  - {m}")
                            text_output.append("\n💡 RECOMMENDATION: Run `ace_index_project(force=True)` to update the index.")
                        else:
                            text_output.append("\n💡 TIP: Try a more general search or check your `file_pattern`.")
                        
                        return [types.TextContent(type="text", text="\n".join(text_output))]

                text_output.append(f"Found {len(documents)} matching files for: {project_path}\n")
                
                MAX_LEN = 1500
                BOOSTED_MAX_LEN = 3000

                for doc, meta in zip(documents, metadatas):
                    path = meta.get('path', 'unknown')
                    is_boosted = meta.get('boosted', False)
                    limit = BOOSTED_MAX_LEN if is_boosted else MAX_LEN
                    
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

            elif name == "ace_index_status":
                path = arguments["project_path"]
                status = indexer.get_index_status(path)
                
                if status["status"] == "error":
                    return [types.TextContent(type="text", text=status["message"])]
                
                import datetime
                dt = datetime.datetime.fromtimestamp(status["last_update"]).strftime('%Y-%m-%d %H:%M:%S')
                
                output = [
                    f"📊 Index Status: {path}",
                    f"• Indexed files: {status['indexed_files_count']}",
                    f"• Last updated: {dt}",
                    f"• New/Changed files on disk (NOT in index): {status['missing_from_index_count']}"
                ]
                
                if status["missing_from_index_count"] > 0:
                    output.append("\n⚠️ Missing files sample:")
                    for f in status["missing_files_sample"]:
                        output.append(f"  - {f}")
                    output.append("\n💡 Recommendation: Run `ace_index_project(force=True)`")
                
                return [types.TextContent(type="text", text="\n".join(output))]

            elif name == "ace_list_indexed":
                path = arguments["project_path"]
                pattern = arguments.get("pattern")
                files = indexer.list_indexed_files(path, pattern)
                
                msg = f"Indexed files ({len(files)}):"
                if len(files) > 50:
                    msg += f"\n(Showing first 50)\n"
                
                file_list = "\n".join(files[:50])
                return [types.TextContent(type="text", text=f"{msg}\n{file_list}")]

            elif name == "ace_index_project":
                project_path = arguments.get("project_path")
                force = arguments.get("force", False)
                stats = indexer.index_project(project_path, force=force)
                
                msg = f"Project Indexed Successfully.\nStats: {stats}"
                return [types.TextContent(type="text", text=msg)]
                
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return [types.TextContent(type="text", text=f"Error executing tool {name}: {str(e)}")]
    
    return app


