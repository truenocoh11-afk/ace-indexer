import asyncio
import sys
import os
import json
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
    
    # State to persist last used project path (In-memory explicitly isolated)
    state = {
        "last_project_path": None
    }

    # UNIFIED: One safe function for all tools.
    # The CWD fallback was removed because in MCP server contexts (Antigravity, Claude Desktop, etc.)
    # os.getcwd() returns the app install directory, not the user's project — causing misleading errors.
    def resolve_project_path(arguments: dict, require_explicit: bool = False) -> str:
        """
        Resolves project_path safely.
        
        Priority:
          1. Explicit argument (always wins, saves to session state).
          2. Session memory (previous call in this session).
          3. Error with clear guidance to call ace_boot_memory first.
        
        Args:
            require_explicit: If True, skips session memory and requires the argument.
        """
        path = arguments.get("project_path")
        
        if path:
            # Normalize to forward slashes for ChromaDB consistency (especially on Windows)
            path = path.replace("\\", "/")
            state["last_project_path"] = path
            return path
        
        if not require_explicit and state["last_project_path"]:
            return state["last_project_path"]
        
        raise ValueError(
            "[ACE] project_path no resuelto. Opciones:\n"
            "1. Pasa project_path='C:\\\\ruta\\\\al\\\\proyecto' explícitamente en esta llamada.\n"
            "2. Llama a ace_boot_memory(project_path='...') primero para establecerlo en la sesión."
        )

    # Keep the strict alias for backwards compatibility (used by ace_boot_memory / ace_update_memory)
    def resolve_project_path_strict(arguments: dict) -> str:
        return resolve_project_path(arguments, require_explicit=True)

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="ace_search_code",
                description="[v1.4] 💎 Hybrid search. format='compact' (default, TSV, 65% fewer tokens) or 'verbose' (full snippets). project_path is OPTIONAL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query"},
                        "project_path": {"type": "string", "description": "Absolute path (optional)"},
                        "file_pattern": {"type": "string", "description": "Optional glob pattern"},
                        "format": {"type": "string", "enum": ["compact", "verbose"], "default": "compact", "description": "compact=TSV high-density (default). verbose=full snippets."},
                        "auto_usages": {"type": "boolean", "description": "Also search for usages of the found symbol. Recommended for impact analysis."},
                        "workspace_only": {"type": "boolean", "description": "Default True. Set False to include remote/synced files."}
                    },
                    "required": ["query"]
                }
            ),
            types.Tool(
                name="ace_remote",
                description="[v1.0] 🌐 Remote sync manager. phase='plan_count' (count files), 'plan_sync' (generate sync commands), 'ingest' (load results).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "phase": {"type": "string", "enum": ["plan_count", "plan_sync", "ingest"], "description": "plan_count=Phase 1, plan_sync=Phase 2, ingest=Phase 3"},
                        "project_path": {"type": "string"},
                        "env_name": {"type": "string", "description": "Env name (loads from .ace/remotes.json if exists)"},
                        "ssh_alias": {"type": "string"}, "ssh_host": {"type": "string"},
                        "identity_file": {"type": "string"}, "remote_path": {"type": "string"},
                        "file_extensions": {"type": "string"}, "exclude_dirs": {"type": "string"}
                    },
                    "required": ["phase", "env_name"]
                }
            ),


            types.Tool(
                name="ace_memory",
                description="[v1.0] 🧠 Session memory. action='boot' (load all memory at session start). action='update' (write to memory). project_path is OPTIONAL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["boot", "update"], "description": "boot=load all, update=write"},
                        "project_path": {"type": "string"},
                        "memory_type": {"type": "string", "enum": ["context", "task", "lessons"], "description": "Required for action=update"},
                        "content": {"type": "string", "description": "Required for action=update"},
                        "append": {"type": "boolean", "default": True},
                        "archive_legacy": {"type": "boolean", "default": False},
                        "force": {"type": "boolean", "default": False}
                    },
                    "required": ["action"]
                }
            ),
            types.Tool(
                name="ace_get_symbol",
                description="[v1.1] 🔍 Read a specific function or class from disk using its line_map position. Equivalent to LazyLoadingAI's get_function. Provide symbol_name and file_path.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "Absolute path (optional)"},
                        "file_path": {"type": "string", "description": "Absolute or relative path to the file"},
                        "symbol_name": {"type": "string", "description": "Function or class name to extract"}
                    },
                    "required": ["file_path", "symbol_name"]
                }
            ),
            types.Tool(
                name="ace_manage_index",
                description="[v1.1] 🗂️ Unified index management: action='status' (health), action='list' (files), action='reindex' (force re-index). Replaces ace_index_status, ace_list_indexed, ace_index_project. project_path is OPTIONAL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                        "action": {"type": "string", "enum": ["status", "list", "reindex"], "description": "status=health, list=files, reindex=force"},
                        "pattern": {"type": "string", "description": "For action=list, optional glob filter"},
                        "extra_ignore_dirs": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["action"]
                }
            ),
            types.Tool(
                name="ace_call_graph",
                description="[v1.2 Fase 3] 🕸️ Show Call Graph for a file. Returns top callees and Mermaid diagram. Powered by Markov chains over ChromaDB calls metadata.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "Absolute path (optional)"},
                        "file_path": {"type": "string", "description": "File to analyze"},
                        "format": {"type": "string", "enum": ["list", "mermaid"], "default": "list"}
                    },
                    "required": ["file_path"]
                }
            ),
            types.Tool(
                name="ace_architecture_overview",
                description="[v1.3] 🗺️ Generate a high-level TSV map of the project architecture. Provides [MODULES], [DEPS], [ENTRY_POINTS], [PUBLIC_API] and [PATTERNS]. Use THIS first to orient yourself in unknown or large codebases without wasting tokens.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "Absolute project path (optional)"},
                        "focus": {
                            "type": "string", 
                            "enum": ["full", "modules", "dependencies", "entry_points", "public_api"],
                            "default": "modules",
                            "description": "Information to focus on. 'full' consumes more tokens."
                        },
                        "debug": {
                            "type": "boolean",
                            "description": "If true, append diagnostic debug information to the output."
                        }
                    }
                }
            ),
            types.Tool(
                name="ace_code_health_scan",
                description="[v1.0 BETA] 🩺 Scan code for 'blind spots' and silent-error anti-patterns (Bare except, empty catch, etc).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "Absolute path (optional)"},
                        "file_pattern": {"type": "string", "description": "Optional glob pattern to filter files"}
                    }
                }
            )
        ]

    def _allocate_budget(total_chars: int, n_results: int, boosts: list) -> list:
        """Distribuye el budget de contexto entre N resultados. Boosted recibe 2x."""
        if n_results == 0:
            return []
        boost_count = sum(1 for b in boosts if b)
        # base * (n_normal + 2 * n_boosted) = total_chars
        # base * (n_results - n_boosted + 2 * n_boosted) = total_chars
        # base * (n_results + n_boosted) = total_chars
        denominator = (n_results + boost_count)
        base = total_chars // denominator if denominator > 0 else total_chars
        return [base * 2 if b else base for b in boosts]

    def _format_compact(documents, metadatas, query, project_path, is_usage_block=False):
        """Formatea resultados en TSV ultra-denso. Soporta bloques de dominó."""
        import os
        lines = []
        if not is_usage_block:
            lines.append(f"[FORMAT v1.1] [SEARCH: {query}] [RESULTS: {len(documents)}]")
        else:
            lines.append(f"[DOMINO: USAGES FOR '{query}'] [RESULTS: {len(documents)}]")

        lines.append("FILE\tTYPE\tFLAGS\tCONF\tLOCATION\tSNIPPET_CHARS")

        for doc, meta in zip(documents, metadatas):
            path = meta.get("path", "unknown")
            try:
                rel_path = os.path.relpath(path, project_path)
            except Exception:
                rel_path = path

            is_remote = meta.get("remote", False)
            env = meta.get("env", "")
            is_boosted = meta.get("boosted", False)
            line_num = meta.get("line", 0)

            flags = []
            if is_remote:
                flags.append(f"REMOTE:{env}")
            if is_boosted:
                flags.append("PRIORITY")

            flags_str = "|".join(flags) if flags else "-"
            
            # Resolve Location (Symbol-aware)
            location = "-"
            if line_num > 0:
                location = f"L{line_num}"
            else:
                # Try line_map from AST (v4.0 Phase A.B)
                line_map_raw = meta.get("line_map", "{}")
                try:
                    line_map = json.loads(line_map_raw) if isinstance(line_map_raw, str) else (line_map_raw or {})
                    # Search for query tokens in map (e.g. "index_project" -> L244)
                    for token in query.replace("(", " ").replace(")", " ").replace(".", " ").split():
                        if token.lower() in [k.lower() for k in line_map.keys()]:
                            # Find exact key to get correct case match
                            for k, v in line_map.items():
                                if k.lower() == token.lower():
                                    location = f"L{v}"
                                    break
                            if location != "-": break
                except Exception:
                    pass
            
            rrf_score = meta.get("rrf_score", 0)
            literal = meta.get("literal_match", False)
            conf = "HIGH" if literal and rrf_score > 0.7 else ("MED" if literal or rrf_score > 0.4 else "LOW")
            boosts = [m.get("boosted", False) for m in metadatas]
            budgets = _allocate_budget(8000, len(documents), boosts)
            # Find index safely if documents is not a list
            docs_list = list(documents)
            doc_idx = docs_list.index(doc) if doc in docs_list else 0
            snippet_limit = budgets[doc_idx] if doc_idx < len(budgets) else 600
            snippet_len = min(len(doc), snippet_limit)
            lines.append(f"{rel_path}\tcode\t{flags_str}\t{conf}\t{location}\t{snippet_len}")

        lines.append("")
        lines.append("===SOURCES===")
        for doc, meta in zip(documents, metadatas):
            path = meta.get("path", "unknown")
            try:
                rel_path = os.path.relpath(path, project_path)
            except Exception:
                rel_path = path
                
            chunk_id = meta.get("chunk_id", "")
            if chunk_id and "::" in chunk_id:
                chunks_parts = chunk_id.split("::")
                id_badge = f"::{chunks_parts[-2]}::{chunks_parts[-1]}" if len(chunks_parts) > 2 else f" ({chunk_id})"
            else:
                id_badge = ""
                
            skeleton = meta.get("skeleton", "")
            boosts = [m.get("boosted", False) for m in metadatas]
            budgets = _allocate_budget(8000, len(documents), boosts)
            docs_list = list(documents)
            doc_idx = docs_list.index(doc) if doc in docs_list else 0
            limit = budgets[doc_idx] if doc_idx < len(budgets) else 600
            
            lines.append(f"--- {rel_path}{id_badge} ---")
            # Preferir skeleton (firmas semánticas) sobre recorte ciego
            if skeleton and len(skeleton) > 50:
                lines.append(skeleton[:limit])
            else:
                lines.append(doc[:limit])

        return "\n".join(lines)

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        sys.stderr.write(f"[DEBUG] call_tool invoked: {name} with {arguments}\n")
        
        try:
            if name == "ace_search_code":
                import re, time, datetime
                start_time = time.time()
                query = arguments.get("query")
                project_path = resolve_project_path(arguments)
                file_pattern = arguments.get("file_pattern")
                fmt = arguments.get("format", "compact")
                auto_usages = arguments.get("auto_usages", False)
                workspace_only = arguments.get("workspace_only", True)

                results = indexer.query(project_path, query, file_pattern=file_pattern, workspace_only=workspace_only)
                q1_duration = time.time() - start_time
                documents = results.get("documents", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]

                if not documents:
                    total_time = time.time() - start_time
                    text_output = [f"[SEARCH] 0 results for: '{query}'"]
                    if any(c in query for c in "().'\""):
                        text_output.append("💡 Hint: Your query looks like code. If literal search failed, try conceptual.")
                    
                    try:
                        status = indexer.get_index_status(project_path)
                        if status.get("status") == "ok":
                            dt = datetime.datetime.fromtimestamp(status["last_update"]).strftime('%Y-%m-%d %H:%M:%S')
                            text_output.append(f"\n📊 Index Status: {status['indexed_files_count']} files | Last updated: {dt}")
                            if status.get("missing_from_index_count", 0) > 0:
                                text_output.append(f"   ⚠️ {status['missing_from_index_count']} unindexed files. Run ace_manage_index(action='reindex')")
                    except Exception:
                        pass
                    return [types.TextContent(type="text", text="\n".join(text_output))]

                if fmt == "verbose":
                    text_output = [f"Found {len(documents)} matching files for: {project_path}\n"]
                    try:
                        status = indexer.get_index_status(project_path)
                        if status["status"] == "ok":
                            dt = datetime.datetime.fromtimestamp(status['last_update']).strftime('%H:%M')
                            text_output.append(f"📊 Index Stats: {status['indexed_files_count']} files | Last updated: {dt}")
                            if status.get("missing_from_index_count", 0) > 0:
                                text_output.append(f"   ⚠️ Warning: {status['missing_from_index_count']} stale files.\n")
                    except: pass

                    for doc, meta in zip(documents, metadatas):
                        path = meta.get('path', 'unknown')
                        is_boosted = meta.get('boosted', False)
                        is_literal = meta.get('literal_match', False)
                        is_remote = meta.get('remote', False)
                        env = meta.get('env')
                        line = meta.get('line', 0)
                        skeleton = meta.get('skeleton', '')
                        
                        match_type = " [LITERAL MATCH] ✅" if is_literal else " [SEMANTIC ONLY] 🧠"
                        remote_badge = f" [REMOTE: {env}] 🌐" if is_remote else ""
                        priority = " [PRIORITY]" if is_boosted else ""
                        
                        text_output.append(f"--- File: {path}{remote_badge}{match_type}{priority} ---")
                        if is_remote:
                            text_output.append("💡 Remote snippet. Use SSH to view full content.")
                        
                        # Phase 1: Intelligent Snippet (Skeleton + Context)
                        snippet = ""
                        if skeleton:
                            # Use first 800 chars of skeleton for structural overview
                            snippet += f"[SKELETON]\n{skeleton[:800]}\n"
                        
                        if line > 0 and not is_remote:
                            # Extract ±10 lines context
                            try:
                                content_lines = doc.splitlines()
                                start = max(0, line - 11)
                                end = min(len(content_lines), line + 10)
                                context = "\n".join([f"{i+1}: {l}" for i, l in enumerate(content_lines[start:end])])
                                snippet += f"\n[CONTEXT L{line}]\n{context}\n"
                            except: pass
                        
                        if not snippet:
                            snippet = doc[:1500] if is_boosted else doc[:800]
                            
                        text_output.append(snippet[:2500]) # Hard limit
                        text_output.append("\n" + "-"*20 + "\n")
                    return [types.TextContent(type="text", text="\n".join(text_output))]

                # DEFAULT: compact
                fmt1_start = time.time()
                output = _format_compact(documents, metadatas, query, project_path)
                fmt1_duration = time.time() - fmt1_start
                usg_duration = 0.0
                if auto_usages and documents:
                    symbol = None
                    best_meta = next((m for m in metadatas if m.get('type') == 'code'), metadatas[0] if metadatas else None)
                    line_map_raw = best_meta.get("line_map", "{}") if best_meta else "{}"
                    try:
                        line_map = json.loads(line_map_raw) if isinstance(line_map_raw, str) else (line_map_raw or {})
                    except Exception: line_map = {}
                    query_tokens = re.split(r'[\s_.()\[\]]+', query.lower())
                    for token in (t for t in query_tokens if len(t) >= 3):
                        for key in line_map:
                            if token in key.lower():
                                symbol = key; break
                        if symbol: break
                    if not symbol and line_map:
                        sorted_syms = sorted(line_map.items(), key=lambda x: x[1])
                        co_symbols = ", ".join(f"{k}:L{v}" for k, v in sorted_syms[:8])
                        output += f"\n📎 Co-located en {os.path.basename(best_meta.get('path','?'))}: {co_symbols}"
                    if symbol and symbol.lower() != query.lower():
                        q2_start = time.time()
                        usg_results = indexer.query(project_path, symbol, workspace_only=workspace_only)
                        usg_docs = usg_results.get("documents", [[]])[0]
                        usg_metas = usg_results.get("metadatas", [[]])[0]
                        if usg_docs:
                            usg_block = _format_compact(usg_docs, usg_metas, symbol, project_path, is_usage_block=True)
                            output += "\n\n" + usg_block
                        elif not usg_docs and line_map:
                            sorted_syms = sorted(line_map.items(), key=lambda x: x[1])
                            co_symbols = ", ".join(f"{k}:L{v}" for k, v in sorted_syms[:8])
                            output += f"\n\n[DOMINO: NO USAGES FOUND] -> Co-located: {co_symbols}"
                        usg_duration = time.time() - q2_start
                total_duration = time.time() - start_time
                output_chars = len(output)
                debug_info = f"\n[DEBUG] Time: {total_duration:.2f}s | Q1: {q1_duration:.2f}s | Fmt: {fmt1_duration:.2f}s | Usages: {usg_duration:.2f}s | Out: {output_chars}ch"
                return [types.TextContent(type="text", text=output + "\n" + debug_info)]

            elif name == "ace_search_code_compact":
                # LEGACY REDIRECT
                arguments["format"] = "compact"
                return await call_tool("ace_search_code", arguments)

            elif name == "ace_get_symbol":
                import linecache, json
                file_path = arguments.get("file_path", "")
                symbol_name = arguments.get("symbol_name", "")
                project_path = resolve_project_path(arguments)
                
                # Resolve relative paths
                if not os.path.isabs(file_path):
                    file_path = os.path.join(project_path, file_path)
                
                # Normalize to forward slashes for index comparison
                file_path = file_path.replace("\\", "/")
                
                if not os.path.exists(file_path):
                    return [types.TextContent(type="text", text=f"❌ File not found: {file_path}")]
                
                # ARCHITECTURAL FIX: Direct ID lookup instead of semantic search
                # Since we have the absolute file_path, we should query ChromaDB directly by ID
                line_map = {}
                found_meta = None
                
                try:
                    # Access the collection directly via indexer's internal store
                    indices_dir, _ = indexer._get_paths(project_path)
                    collection = indexer._store.get_collection(project_path, indices_dir)
                    if collection:
                        # ChromaDB uses path as ID
                        res = collection.get(ids=[file_path], include=["metadatas"])
                        if res and res["metadatas"]:
                            found_meta = res["metadatas"][0]
                            line_map = json.loads(found_meta.get("line_map", "{}"))
                except Exception as e:
                    # Fallback to fuzzy search in case of direct lookup error
                    sys.stderr.write(f"[DEBUG] Direct lookup failed for {file_path}: {e}. Falling back to fuzzy search.\n")
                    results = indexer.query(project_path, symbol_name, file_pattern=os.path.basename(file_path))
                    metadatas = results.get("metadatas", [])
                    for meta in metadatas:
                        if meta.get("path") == file_path:
                            found_meta = meta
                            line_map = json.loads(meta.get("line_map", "{}"))
                            break
                
                start_line = None
                if line_map:
                    # Find exact or partial match
                    for k, v in line_map.items():
                        if k.lower() == symbol_name.lower() or symbol_name.lower() in k.lower():
                            start_line = v
                            break
                
                if start_line is None:
                    return [types.TextContent(type="text", text=f"❌ Symbol '{symbol_name}' not found in index for {file_path}. Try ace_manage_index(action='reindex') first.")]
                
                # Read ~60 lines from start_line
                lines = []
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        all_lines = f.readlines()
                    lines = all_lines[max(0, start_line - 1):start_line + 60]
                except Exception as e:
                    return [types.TextContent(type="text", text=f"❌ Read error: {e}")]
                
                output = f"# {symbol_name} @ {os.path.relpath(file_path, project_path)}:L{start_line}\n"
                output += "".join(lines)
                return [types.TextContent(type="text", text=output)]

            elif name == "ace_index_status":
                # LEGACY REDIRECT
                arguments["action"] = "status"
                return await call_tool("ace_manage_index", arguments)

            elif name == "ace_list_indexed":
                # LEGACY REDIRECT
                arguments["action"] = "list"
                return await call_tool("ace_manage_index", arguments)

            elif name == "ace_index_project":
                # LEGACY REDIRECT
                arguments["action"] = "reindex"
                return await call_tool("ace_manage_index", arguments)

            elif name == "ace_manage_index":
                action = arguments.get("action", "status")
                project_path = resolve_project_path(arguments)
                
                if action == "status":
                    status = indexer.get_index_status(project_path)
                    if status["status"] == "error":
                        return [types.TextContent(type="text", text=status["message"])]
                    import datetime
                    dt = datetime.datetime.fromtimestamp(status["last_update"]).strftime('%Y-%m-%d %H:%M:%S')
                    out = [f"📊 Index: {project_path}", f"• Files: {status['indexed_files_count']}", f"• Updated: {dt}"]
                    if status.get("missing_from_index_count", 0) > 0:
                        out.append(f"• ⚠️ {status['missing_from_index_count']} unindexed files")
                    return [types.TextContent(type="text", text="\n".join(out))]
                
                elif action == "list":
                    pattern = arguments.get("pattern", "")
                    files = indexer.list_indexed_files(project_path, pattern)
                    file_list = "\n".join(files[:50])
                    return [types.TextContent(type="text", text=f"Indexed files ({len(files)}):\n{file_list}")]
                
                elif action == "reindex":
                    extra_ignore = arguments.get("extra_ignore_dirs", [])
                    stats = indexer.index_project(project_path, force=True, extra_ignore_dirs=extra_ignore)
                    return [types.TextContent(type="text", text=f"Project Indexed Successfully.\nStats: {stats}")]
                
                return [types.TextContent(type="text", text=f"❌ Unknown action: {action}")]

            elif name == "ace_memory":
                from core.memory import MemoryManager
                action = arguments.get("action")
                project_path = resolve_project_path_strict(arguments)
                manager = MemoryManager(project_path)
                if action == "boot":
                    content = manager.read("all")
                    return [types.TextContent(type="text", text=content)]
                elif action == "update":
                    memory_type = arguments.get("memory_type")
                    content = arguments.get("content")
                    if not memory_type or not content:
                        return [types.TextContent(type="text", text="❌ action=update requires 'memory_type' and 'content'.")]
                    append = arguments.get("append", True)
                    force = arguments.get("force", False)
                    archive_legacy = arguments.get("archive_legacy", False)
                    result = manager.write(memory_type, content, append=append, force=force, archive_legacy=archive_legacy)
                    return [types.TextContent(type="text", text=result)]
                return [types.TextContent(type="text", text=f"❌ Unknown action: {action}. Use 'boot' or 'update'.")]

            elif name in ("ace_boot_memory", "ace_update_memory"):
                # LEGACY REDIRECT
                arguments["action"] = "boot" if name == "ace_boot_memory" else "update"
                return await call_tool("ace_memory", arguments)

            elif name == "ace_remote":
                phase = arguments.get("phase")
                project_path = resolve_project_path(arguments)
                env_name = arguments.get("env_name")
                remote_indexer = RemoteIndexer(project_path)
                if phase == "plan_count":
                    result = remote_indexer.get_count_command(env_name=env_name, ssh_alias=arguments.get("ssh_alias"), ssh_host=arguments.get("ssh_host"), identity_file=arguments.get("identity_file"), remote_path=arguments.get("remote_path"), file_extensions=arguments.get("file_extensions"), exclude_dirs=arguments.get("exclude_dirs"))
                    return [types.TextContent(type="text", text=f"🌐 Phase 1: Count Remote Files\n\n```bash\n{result['command']}\n```\n\nSi es correcto, continúa con phase='plan_sync'.")]
                elif phase == "plan_sync":
                    result = remote_indexer.get_sync_command(env_name=env_name, ssh_alias=arguments.get("ssh_alias"), ssh_host=arguments.get("ssh_host"), identity_file=arguments.get("identity_file"), remote_path=arguments.get("remote_path"), file_extensions=arguments.get("file_extensions"), exclude_dirs=arguments.get("exclude_dirs"))
                    return [types.TextContent(type="text", text=f"🚀 Phase 2: Full Remote Sync\n\n1. SCP script:\n```bash\n{result['scp_command']}\n```\n\n2. Ejecutar:\n```bash\n{result['exec_command']} > \"{result['output_path']}\"\n```\n\nLuego: phase='ingest'")]
                elif phase == "ingest":
                    data = remote_indexer.ingest_cache(env_name)
                    # Ingest into local vector store
                    stats = indexer.index_remote_data(project_path, data)
                    return [types.TextContent(type="text", text=f"✅ Remote ingested for '{env_name}'. Files: {stats['indexed']}")]
                return [types.TextContent(type="text", text=f"❌ Unknown phase: {phase}. Use plan_count, plan_sync, or ingest.")]

            elif name in ("ace_sync_remote_index", "ace_sync_remote_execute", "ace_ingest_remote_data"):
                # LEGACY REDIRECT
                phase_map = {"ace_sync_remote_index": "plan_count", "ace_sync_remote_execute": "plan_sync", "ace_ingest_remote_data": "ingest"}
                arguments["phase"] = phase_map[name]
                return await call_tool("ace_remote", arguments)

            elif name == "ace_code_health_scan":
                from core.skeletonizer import Skeletonizer
                import fnmatch
                project_path = resolve_project_path(arguments)
                file_pattern = arguments.get("file_pattern", "*")
                
                skeletonizer = Skeletonizer()
                all_diagnostics = []
                
                # Scan files
                for root, _, files in os.walk(project_path):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, project_path).replace("\\", "/")
                        
                        if fnmatch.fnmatch(rel_path, file_pattern) or fnmatch.fnmatch(file, file_pattern):
                            # Skip common binary/ignore dirs
                            if any(d in rel_path.split("/") for d in (".git", "node_modules", "venv", ".next", "__pycache__")):
                                continue
                            
                            try:
                                with open(full_path, "r", encoding="utf-8") as f:
                                    code = f.read()
                                
                                results = skeletonizer.scan_blind_spots(code, full_path)
                                if results:
                                    for res in results:
                                        res["file"] = rel_path
                                        all_diagnostics.append(res)
                            except Exception:
                                continue

                if not all_diagnostics:
                    return [types.TextContent(type="text", text="✅ No blind spots found. Code looks healthy!")]
                
                # Format output
                output = ["🩺 **ACE Health Scan Results**\n"]
                for diag in all_diagnostics:
                    output.append(f"- `[{diag['file']}:{diag['line']}]` {diag['message']} (type: {diag['type']})")
                
                return [types.TextContent(type="text", text="\n".join(output))]

            elif name == "ace_call_graph":
                from core.markov import MarkovCallGraph
                project_path = resolve_project_path(arguments)
                file_path = arguments.get("file_path", "")
                fmt = arguments.get("format", "list")
                
                # Cargar toda la metadata del index para construir el grafo de forma eficiente
                indices_dir, _ = indexer._get_paths(project_path)
                collection = indexer._store.get_collection(project_path, indices_dir)
                if not collection:
                    return [types.TextContent(type="text", text="❌ Chroma collection not found. Re-index first.")]
                
                # Usar get() es más directo que query() para "traer todo"
                results = collection.get(include=["metadatas"])
                all_metas = results.get("metadatas", [])
                
                graph = MarkovCallGraph()
                graph.ingest_chroma_metadata(all_metas)
                
                abs_path = file_path if os.path.isabs(file_path) else os.path.join(project_path, file_path)
                # Normalize to forward slashes for matching ChromaDB-sourced metadata
                abs_path = abs_path.replace("\\", "/")
                file_path = file_path.replace("\\", "/")
                
                # Delegamos normalización cross-platform a markov.py, evitando corromper la ruta local.
                
                if fmt == "mermaid":
                    return [types.TextContent(type="text", text=graph.to_mermaid())]
                
                # Intentar con la ruta relativa primero (como guarda ChromaDB)
                top = graph.get_top_callees(file_path, top_n=15)
                if not top:
                    top = graph.get_top_callees(abs_path, top_n=15)
                if not top:
                    known = list(graph.transitions.keys())[:5]
                    hint = f"\nArchivos con calls: {known}" if known else "\n⚠️ Ningún archivo tiene calls. Verifica el skeletonizer."
                    return [types.TextContent(type="text", text=f"❌ No call data for {file_path}.{hint}")]
                
                return [types.TextContent(type="text", text="\n".join([f"{c}: {p*100:.1f}%" for c, p in top]))]

            elif name == "ace_architecture_overview":
                project_path = resolve_project_path(arguments)
                focus = arguments.get("focus", "full")
                
                indices_dir, _ = indexer._get_paths(project_path)
                collection = indexer._store.get_collection(project_path, indices_dir)
                if not collection:
                    return [types.TextContent(type="text", text="❌ Chroma collection not found. Re-index first.")]
                
                import json
                
                # --- BUGFIX: Fallback robusto con SQLite directo ---
                # Debido a una incompatibilidad de versiones en ChromaDB (v0.4.22 vs Schema v10),
                # el método `collection.get()` devuelve metadatos vacíos para 'line_map'.
                # Leemos la base de datos SQLite directamente para garantizar la extracción correcta.
                db_path = os.path.join(indices_dir, "chroma_db", "chroma.sqlite3")
                code_metas = []
                
                if os.path.exists(db_path):
                    import sqlite3
                    try:
                        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                        c = conn.cursor()
                        # Extraer solo archivos de tipo 'code' y su line_map usando solo la tabla de metadatos
                        c.execute('''
                            SELECT 
                                MAX(CASE WHEN key = 'path' THEN string_value END) as path,
                                MAX(CASE WHEN key = 'line_map' THEN string_value END) as line_map
                            FROM embedding_metadata
                            GROUP BY id
                            HAVING MAX(CASE WHEN key = 'type' THEN string_value END) = 'code'
                        ''')
                        for row in c.fetchall():
                            if row[0]: # path no es None
                                code_metas.append({
                                    "path": row[0],
                                    "line_map": row[1] or "{}"
                                })
                        conn.close()
                    except Exception as e:
                        return [types.TextContent(type="text", text=f"❌ SQL Extract Error: {e}")]
                else:
                    return [types.TextContent(type="text", text="❌ SQLite DB not found. Re-index first.")]
                
                if not code_metas:
                    return [types.TextContent(type="text", text="❌ No code metadata found in database.")]
                
                from collections import defaultdict
                modules_map = defaultdict(lambda: {"files": 0, "api_count": 0})
                global_api = []
                entry_points = []
                
                for m in code_metas:
                    fpath = m.get("path", "")
                    try:
                        rel = os.path.relpath(fpath, project_path).replace("\\", "/")
                    except Exception:
                        rel = fpath.replace("\\", "/")
                    
                    mod_name = rel.split("/")[0] if "/" in rel else "/"
                    modules_map[mod_name]["files"] += 1
                    
                    # Detectar entry points por convención de nombre
                    if any(x in rel.lower() for x in ["main.py", "__main__.py", "cli.py", "index.ts", "index.js", "setup.py", "app."]):
                        entry_points.append(rel)
                    
                    parse_errors = []
                    try:
                        raw_lmap = m.get("line_map", "{}")
                        lmap = json.loads(raw_lmap)
                    except Exception as je:
                        parse_errors.append(f"{rel}: {type(je).__name__}: {je} | raw={repr(raw_lmap[:60])}")
                        lmap = {}
                    
                    global_api.extend([(sym, rel, ln) for sym, ln in lmap.items()])
                    modules_map[mod_name]["api_count"] += len(lmap)
                
                # Calcular dependencias (Naive) a través de calls -> api map
                deps = defaultdict(set)
                if focus in ["full", "dependencies"]:
                    sym_file_map = {sym: rel for sym, rel, _ in global_api}
                    for m in code_metas:
                        try:
                            fpath = m.get("path", "")
                            try:
                                rel = os.path.relpath(fpath, project_path).replace("\\", "/")
                            except Exception:
                                rel = fpath.replace("\\", "/")
                            mod_source = rel.split("/")[0] if "/" in rel else "/"
                            calls = json.loads(m.get("calls", "[]"))
                            for c in calls:
                                if c in sym_file_map:
                                    mod_target = sym_file_map[c].split("/")[0] if "/" in sym_file_map[c] else "/"
                                    if mod_source != mod_target:
                                        deps[mod_source].add(mod_target)
                        except Exception:
                            continue

                lines = [f"# Architecture Overview: {os.path.basename(project_path)}", f"Focus: {focus}\n"]
                
                if focus in ["full", "modules"]:
                    lines.append("## [MODULES]")
                    lines.append("MODULE\tFILES\tEXPORTS")
                    for mod, stats in sorted(modules_map.items(), key=lambda x: x[1]['files'], reverse=True)[:20]:
                        lines.append(f"{mod}\t{stats['files']}\t{stats['api_count']}")
                    lines.append("")
                
                if focus in ["full", "dependencies"]:
                    lines.append("## [DEPS] (Cross-module calls)")
                    lines.append("FROM_MODULE\tTO_MODULE")
                    for src, tgts in sorted(deps.items()):
                        lines.append(f"{src}\t{', '.join(sorted(list(tgts)))}")
                    lines.append("")
                
                if focus in ["full", "entry_points", "modules"]:
                    lines.append("## [ENTRY_POINTS]")
                    for ep in entry_points[:10]:
                        lines.append(f"- {ep}")
                    lines.append("")
                
                if focus in ["full", "public_api"]:
                    lines.append("## [PUBLIC_API] (Top 50 symbols)")
                    lines.append("SYMBOL\tFILE\tLINE")
                    for sym, rel, ln in sorted(global_api)[:50]:
                        lines.append(f"{sym}\t{rel}\tL{ln}")
                    lines.append("")
                
                # Optional diagnostic block
                if arguments.get("debug", False):
                    lmap_none = sum(1 for m in code_metas if m.get("line_map") is None)
                    lmap_empty = sum(1 for m in code_metas if m.get("line_map") == "{}")
                    lmap_has = sum(1 for m in code_metas if m.get("line_map") not in (None, "{}"))
                    samples = []
                    for m in code_metas[:5]:
                        raw = m.get("line_map")
                        samples.append(f"type={type(raw).__name__} len={len(raw) if raw else 0} val={repr(raw[:80]) if raw else 'None'}")
                    # Also check what keys exist in embedding_metadata
                    try:
                        conn2 = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                        c2 = conn2.cursor()
                        c2.execute("SELECT DISTINCT key FROM embedding_metadata LIMIT 20")
                        all_keys = [r[0] for r in c2.fetchall()]
                        c2.execute("SELECT string_value FROM embedding_metadata WHERE key='line_map' AND string_value IS NOT NULL AND string_value != '{}' LIMIT 1")
                        raw_sample = c2.fetchone()
                        raw_sample_val = repr(raw_sample[0][:120]) if raw_sample else "NO_ROWS"
                        conn2.close()
                    except Exception as ex:
                        all_keys = [f"ERR: {ex}"]
                        raw_sample_val = "ERR"
                    lines.append(f"## [DEBUG] code_metas={len(code_metas)} global_api={len(global_api)} lmap_none={lmap_none} lmap_empty={lmap_empty} lmap_has={lmap_has}")
                    lines.append(f"## [DEBUG_KEYS] {all_keys}")
                    lines.append(f"## [DEBUG_RAW_SAMPLE] {raw_sample_val}")
                    lines.append(f"## [DEBUG_SAMPLES] {' | '.join(samples)}")
                    # Show non-empty line_map samples and any parse errors
                    nonempty_samples = [(m.get('path','?'), m.get('line_map','')) for m in code_metas if m.get('line_map') not in (None, '{}')][:3]
                    for p, lm in nonempty_samples:
                        try:
                            parsed = json.loads(lm)
                            lines.append(f"## [DEBUG_NONEMPTY] path={p[-40:]} parsed_keys={list(parsed.keys())[:5]}")
                        except Exception as je:
                            lines.append(f"## [DEBUG_NONEMPTY_ERR] path={p[-40:]} err={je} raw={repr(lm[:60])}")

                return [types.TextContent(type="text", text="\n".join(lines))]
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return [types.TextContent(type="text", text=f"Error executing tool {name}: {str(e)}")]
    
    return app
