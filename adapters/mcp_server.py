import asyncio
import sys
import os
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
import mcp.types as types

# Direct Import of Core Logic (No HTTP)
from core.indexer import Indexer
from core.remote_indexer import RemoteIndexer


# Expose the server instance creation
def create_mcp_server():
    app = Server("Antigravity Context Engine (ACE)")
    indexer = Indexer()
    
    # State to persist last used project path (In-memory)
    state = {
        "last_project_path": None
    }
    
    # Persistencia de ruta entre reinicios del servidor (File-based)
    PATH_STORAGE = os.path.join(os.path.expanduser("~"), ".ace_last_path")

    def resolve_project_path(arguments: dict) -> str:
        """Infiere el project_path si no se provee."""
        path = arguments.get("project_path")
        
        # 1. Si el usuario provee uno, mandatorio usarlo y guardarlo
        if path:
            state["last_project_path"] = path
            try:
                with open(PATH_STORAGE, "w") as f:
                    f.write(path)
            except: pass
            return path
        
        # 2. Si ya lo tenemos en memoria en esta sesión
        if state["last_project_path"]:
            return state["last_project_path"]
        
        # 3. Si existe en el archivo de persistencia
        if os.path.exists(PATH_STORAGE):
            try:
                with open(PATH_STORAGE, "r") as f:
                    p = f.read().strip()
                    if os.path.exists(p):
                        state["last_project_path"] = p
                        return p
            except: pass
        
        # 4. Fallback final al CWD
        cwd = os.getcwd()
        sys.stderr.write(f"[WARN] No project_path provided. Falling back to CWD: {cwd}\n")
        state["last_project_path"] = cwd
        return cwd

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="ace_search_code",
                description="[v0.8.2] 💎 Hybrid search (Health, Hints & Remote). project_path is OPTIONAL.",



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
                name="ace_search_code_compact",
                description="[BETA v1.0] ⚡ High-density TSV output. Same search power as ace_search_code but 50-70% fewer tokens. PREFER THIS for architecture queries, exploration, and when searching many files. Returns TSV rows + ===SOURCE=== blocks.",
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
                name="ace_sync_remote_index",
                description="[v0.9.1] 🌐 Phase 1: Generate command to count remote files (Delegate Mode).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                        "env_name": {"type": "string", "description": "Env name (loads from .ace/remotes.json if exists)"},
                        "ssh_alias": {"type": "string", "description": "SSH alias from ~/.ssh/config"},
                        "ssh_host": {"type": "string", "description": "Direct SSH host (user@ip)"},
                        "identity_file": {"type": "string", "description": "Path to SSH key"},
                        "remote_path": {"type": "string", "description": "Path on remote server"},
                        "file_extensions": {"type": "string", "description": "Comma-separated extensions"},
                        "exclude_dirs": {"type": "string", "description": "Comma-separated dirs to skip"}
                    },
                    "required": ["env_name"]
                }
            ),
            types.Tool(
                name="ace_sync_remote_execute",
                description="[v0.9.1] 🚀 Phase 2: Generate commands for full remote sync (Delegate Mode).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                        "env_name": {"type": "string", "description": "Env name"},
                        "ssh_alias": {"type": "string"},
                        "ssh_host": {"type": "string"},
                        "identity_file": {"type": "string"},
                        "remote_path": {"type": "string"},
                        "file_extensions": {"type": "string"},
                        "exclude_dirs": {"type": "string"}
                    },
                    "required": ["env_name"]
                }
            ),
            types.Tool(
                name="ace_ingest_remote_data",
                description="[v0.9.0] ✅ Phase 3: Ingest results from local cache and index them.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                        "env_name": {"type": "string", "description": "Env name"}
                    },
                    "required": ["env_name"]
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

    def _format_compact(documents, metadatas, query, project_path):
        """Formatea resultados en TSV ultra-denso para minimizar consumo de tokens."""
        lines = []
        lines.append(f"[SEARCH: {query}] [RESULTS: {len(documents)}]")
        lines.append("FILE\tTYPE\tFLAGS\tSNIPPET_CHARS")

        for doc, meta in zip(documents, metadatas):
            path = meta.get("path", "unknown")
            is_remote = meta.get("remote", False)
            env = meta.get("env", "")
            is_boosted = meta.get("boosted", False)

            flags = []
            if is_remote:
                flags.append(f"REMOTE:{env}")
            if is_boosted:
                flags.append("PRIORITY")

            rel_path = path
            try:
                import os
                rel_path = os.path.relpath(path, project_path)
            except Exception:
                pass

            flags_str = "|".join(flags) if flags else "-"
            snippet_len = min(len(doc), 600)
            lines.append(f"{rel_path}\tcode\t{flags_str}\t{snippet_len}")

        lines.append("")
        lines.append("===SOURCES===")
        for doc, meta in zip(documents, metadatas):
            path = meta.get("path", "unknown")
            is_boosted = meta.get("boosted", False)
            try:
                import os
                rel_path = os.path.relpath(path, project_path)
            except Exception:
                rel_path = path
            limit = 800 if is_boosted else 400
            lines.append(f"--- {rel_path} ---")
            lines.append(doc[:limit])

        return "\n".join(lines)

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
                        
                        # [Phase B: Query Hints]
                        if any(c in query for c in "().'\""):
                            text_output.append(f"💡 Hint: Your query looks like code. If literal search failed, try a conceptual query (e.g., 'logic for launch display' instead of 'app.get(\"/api/launches\")')")
                        
                        # [Phase A: Index Health]
                        try:
                            status = indexer.get_index_status(project_path)
                            if status["status"] == "ok":
                                import datetime
                                dt = datetime.datetime.fromtimestamp(status["last_update"]).strftime('%Y-%m-%d %H:%M:%S')
                                text_output.append(f"\n📊 Index Health:")
                                text_output.append(f"   • Files indexed: {status['indexed_files_count']}")
                                text_output.append(f"   • Last updated: {dt}")
                                if status.get("missing_from_index_count", 0) > 0:
                                    text_output.append(f"   • ⚠️ {status['missing_from_index_count']} files on disk not in index. Run ace_index_project(force=True) to sync.")
                        except: pass
                        
                        return [types.TextContent(type="text", text="\n".join(text_output))]

                text_output.append(f"Found {len(documents)} matching files for: {project_path}\n")
                
                # [Phase A: Proactive Health Info even with results]
                try:
                    status = indexer.get_index_status(project_path)
                    if status["status"] == "ok":
                        text_output.append(f"📊 Index Stats: {status['indexed_files_count']} files | Last updated: {datetime.datetime.fromtimestamp(status['last_update']).strftime('%H:%M')}")
                        if status.get("missing_from_index_count", 0) > 0:
                            text_output.append(f"   ⚠️ Warning: {status['missing_from_index_count']} stale files. Consider re-indexing.\n")
                except: pass

                
                for doc, meta in zip(documents, metadatas):
                    path = meta.get('path', 'unknown')
                    is_boosted = meta.get('boosted', False)
                    is_literal = meta.get('literal_match', False)
                    is_remote = meta.get('remote', False)
                    env = meta.get('env')
                    
                    # Labels and Badges
                    match_type = " [LITERAL MATCH] ✅" if is_literal else " [SEMANTIC ONLY] 🧠"
                    remote_badge = f" [REMOTE: {env}] 🌐" if is_remote else ""
                    priority = " [PRIORITY]" if is_boosted else ""
                    
                    text_output.append(f"--- File: {path}{remote_badge}{match_type}{priority} ---")
                    
                    # For remote files, add hint on how to view full content
                    if is_remote:
                        # Try to guess SSH alias from remotes.json or use a generic hint
                        text_output.append(f"💡 Remote snippet. Use SSH to view full content.")
                    
                    text_output.append(doc[:3000] if is_boosted else doc[:1500])
                    text_output.append("\n" + "-"*20 + "\n")
                
                return [types.TextContent(type="text", text="\n".join(text_output))]
            
            elif name == "ace_search_code_compact":
                query = arguments.get("query")
                project_path = resolve_project_path(arguments)
                file_pattern = arguments.get("file_pattern")

                results = indexer.query(project_path, query, file_pattern=file_pattern)

                documents = results.get("documents", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]

                if not documents:
                    return [types.TextContent(type="text", text=f"[COMPACT] 0 results for: '{query}'. Try ace_search_code for hints.")]

                output = _format_compact(documents, metadatas, query, project_path)
                return [types.TextContent(type="text", text=output)]

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
                # ... [omitted identical logic] ...
                from core.memory import MemoryManager
                project_path = resolve_project_path(arguments)
                memory_type = arguments.get("memory_type")
                content = arguments.get("content")
                append = arguments.get("append", False)
                manager = MemoryManager(project_path)
                result = manager.write(memory_type, content, append)
                return [types.TextContent(type="text", text=result)]
                
            elif name == "ace_sync_remote_index":
                project_path = resolve_project_path(arguments)
                env_name = arguments.get("env_name")
                
                remote_indexer = RemoteIndexer(project_path)
                result = remote_indexer.get_count_command(
                    env_name=env_name,
                    ssh_alias=arguments.get("ssh_alias"),
                    ssh_host=arguments.get("ssh_host"),
                    identity_file=arguments.get("identity_file"),
                    remote_path=arguments.get("remote_path"),
                    file_extensions=arguments.get("file_extensions"),
                    exclude_dirs=arguments.get("exclude_dirs")
                )
                
                msg = (
                    f"🌐 Phase 1: Count Remote Files (Delegate Mode)\n"
                    f"Ejecuta este comando en tu terminal para contar los archivos:\n\n"
                    f"```bash\n{result['command']}\n```\n\n"
                    f"Si el número es correcto, procede con `ace_sync_remote_execute` para generar el comando de sincronización completa."
                )
                return [types.TextContent(type="text", text=msg)]

            elif name == "ace_sync_remote_execute":
                project_path = resolve_project_path(arguments)
                env_name = arguments.get("env_name")
                
                remote_indexer = RemoteIndexer(project_path)
                result = remote_indexer.get_sync_command(
                    env_name=env_name,
                    ssh_alias=arguments.get("ssh_alias"),
                    ssh_host=arguments.get("ssh_host"),
                    identity_file=arguments.get("identity_file"),
                    remote_path=arguments.get("remote_path"),
                    file_extensions=arguments.get("file_extensions"),
                    exclude_dirs=arguments.get("exclude_dirs")
                )
                
                msg = (
                    f"🚀 Phase 2: Full Remote Sync (Delegate Mode v0.9.1)\n"
                    f"Sigue estos pasos para sincronizar el código remoto:\n\n"
                    f"1. **Subir Script**: Copia el script de indexación al servidor:\n"
                    f"```bash\n{result['scp_command']}\n```\n\n"
                    f"2. **Ejecutar e Indexar**: Ejecuta el script y guarda el resultado localmente:\n"
                    f"```bash\n{result['exec_command']} > \"{result['output_path']}\"\n```\n\n"
                    f"Una vez completado, llama a `ace_ingest_remote_data(env_name=\"{env_name}\")` para cargar los resultados."
                )
                return [types.TextContent(type="text", text=msg)]

            elif name == "ace_ingest_remote_data":
                project_path = resolve_project_path(arguments)
                env_name = arguments.get("env_name")
                
                remote_indexer = RemoteIndexer(project_path)
                data = remote_indexer.ingest_cache(env_name)
                
                # Ingest into local vector store
                ingest_stats = indexer.index_remote_data(project_path, data)
                
                return [types.TextContent(type="text", text=f"✅ Remote Data Ingested for '{env_name}'.\nFiles indexed: {ingest_stats['indexed']}\nAll remote snippets are now searchable locally.")]



                
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return [types.TextContent(type="text", text=f"Error executing tool {name}: {str(e)}")]
    
    return app
