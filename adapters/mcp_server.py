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
                        "file_pattern": {"type": "string", "description": "Optional glob pattern"},
                        "auto_usages": {"type": "boolean", "description": "RECOMENDADO para refactorizaciones o investigación de impacto. Actívalo si necesitas ver dónde se usa el símbolo encontrado para evitar segundas consultas."},
                        "workspace_only": {"type": "boolean", "description": "Default True. Set False to include remote/synced files in results."}
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
                        "force": {"type": "boolean"},
                        "extra_ignore_dirs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Additional directory names to ignore during indexing (e.g. ['site-packages', 'wheels'])"
                        }
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
                description="Update memory. By default, appends content to the existing file. If the existing context is contradictory or confusing, use archive_legacy=True to move it to a legacy section. To completely wipe it, use force=True. project_path is OPTIONAL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                        "memory_type": {"type": "string", "enum": ["context", "task", "lessons"]},
                        "content": {"type": "string"},
                        "append": {"type": "boolean", "default": True, "description": "Add content to the bottom of the existing file."},
                        "archive_legacy": {"type": "boolean", "default": False, "description": "Move existing context to a 'Legacy' section and put new content at the top. Use ONLY if the original context is confusing or contradictory."},
                        "force": {"type": "boolean", "description": "Set to True ONLY to completely wipe the file.", "default": False}
                    },
                    "required": ["memory_type", "content"]
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
                        }
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
            skeleton = meta.get("skeleton", "")
            boosts = [m.get("boosted", False) for m in metadatas]
            budgets = _allocate_budget(8000, len(documents), boosts)
            docs_list = list(documents)
            doc_idx = docs_list.index(doc) if doc in docs_list else 0
            limit = budgets[doc_idx] if doc_idx < len(budgets) else 600
            lines.append(f"--- {rel_path} ---")
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
                import re
                import time
                start_time = time.time()

                query = arguments.get("query")
                project_path = resolve_project_path(arguments)
                file_pattern = arguments.get("file_pattern")
                auto_usages = arguments.get("auto_usages", False)
                workspace_only = arguments.get("workspace_only", True)

                results = indexer.query(project_path, query, file_pattern=file_pattern, workspace_only=workspace_only)
                q1_duration = time.time() - start_time

                documents = results.get("documents", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]

                if not documents:
                    total_time = time.time() - start_time
                    hints = [f"[COMPACT] 0 results for: '{query}'"]
                    if any(c in query for c in "().'\""):
                        hints.append("💡 Try conceptual: describe what the code does instead of pasting syntax")
                    if "_" in query and len(query.split()) == 1:
                        parts = query.split("_")
                        hints.append(f"💡 Try broader: '{' '.join(parts)}'")
                    elif len(query.split()) == 1:
                        hints.append(f"💡 Try: 'where is {query} defined' or file_pattern='*.py'")
                    try:
                        status = indexer.get_index_status(project_path)
                        if status.get("status") == "ok":
                            hints.append(f"📊 INDEX: {status['indexed_files_count']} files")
                            if status.get("missing_from_index_count", 0) > 0:
                                hints.append(f"⚠️ {status['missing_from_index_count']} unindexed files. Run ace_index_project(force=True)")
                    except Exception:
                        pass
                    hints.append(f"[TIME: {total_time:.2f}s]")
                    return [types.TextContent(type="text", text="\n".join(hints))]

                fmt1_start = time.time()
                output = _format_compact(documents, metadatas, query, project_path)
                fmt1_duration = time.time() - fmt1_start

                usg_duration = 0.0
                if auto_usages and documents:
                    symbol = None
                    # [v1.1.1] Prioritize code files for line_map extraction
                    # Find first metadata that is 'code' or has valid line_map
                    best_meta = None
                    for m in metadatas:
                        if m.get('type') == 'code':
                            best_meta = m
                            break
                    if not best_meta and metadatas:
                        best_meta = metadatas[0]
                    
                    line_map_raw = best_meta.get("line_map", "{}") if best_meta else "{}"
                    try:
                        line_map = json.loads(line_map_raw) if isinstance(line_map_raw, str) else (line_map_raw or {})
                    except Exception:
                        line_map = {}
                    query_tokens = re.split(r'[\s_.()\[\]]+', query.lower())
                    for token in query_tokens:
                        if len(token) < 3:
                            continue
                        for key in line_map:
                            if token in key.lower():
                                symbol = key
                                break
                        if symbol:
                            break
                    if not symbol and line_map:
                        # [Bugfix_OPT3] & [V2-D] Immediate co-located fallback instead of blind regex
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
                        elif not usg_docs:
                             # [V2-D] Fallback: Co-located symbols
                            line_map_raw = metadatas[0].get("line_map", "{}") if metadatas else "{}"
                            try:
                                line_map = json.loads(line_map_raw) if isinstance(line_map_raw, str) else (line_map_raw or {})
                                if line_map:
                                    # Sort by line number
                                    sorted_syms = sorted(line_map.items(), key=lambda x: x[1])
                                    # Take up to 8 symbols
                                    co_symbols = ", ".join(f"{k}:L{v}" for k, v in sorted_syms[:8])
                                    output += f"\n\n[DOMINO: NO USAGES FOUND] -> Co-located symbols in {metadatas[0].get('path','?')}:\n📎 {co_symbols}"
                            except Exception:
                                pass
                        usg_duration = time.time() - q2_start

                total_duration = time.time() - start_time
                output_chars = len(output)
                full_estimate = int(output_chars * 2.5)
                savings_pct = max(0, int((1 - output_chars / max(full_estimate, 1)) * 100))
                debug_info = f"\n[DEBUG] Time: {total_duration:.2f}s | Q1: {q1_duration:.2f}s | Fmt: {fmt1_duration:.2f}s | Usages: {usg_duration:.2f}s | Out: {output_chars}ch (~{output_chars//4}tok) | ~{savings_pct}% saved"
                output = output + "\n" + debug_info

                return [types.TextContent(type="text", text=output)]

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

            elif name == "ace_boot_memory":
                from core.memory import MemoryManager
                project_path = resolve_project_path_strict(arguments)
                manager = MemoryManager(project_path)
                content = manager.read("all")
                return [types.TextContent(type="text", text=content)]

            elif name == "ace_update_memory":
                # ... [omitted identical logic] ...
                from core.memory import MemoryManager
                project_path = resolve_project_path_strict(arguments)
                memory_type = arguments.get("memory_type")
                content = arguments.get("content")
                append = arguments.get("append", True) # Default to True
                force = arguments.get("force", False)
                archive_legacy = arguments.get("archive_legacy", False)
                manager = MemoryManager(project_path)
                result = manager.write(memory_type, content, append=append, force=force, archive_legacy=archive_legacy)
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
                        # Extraer solo archivos de tipo 'code' y su line_map
                        c.execute('''
                            SELECT 
                                MAX(CASE WHEN em.key = 'path' THEN em.string_value END) as path,
                                MAX(CASE WHEN em.key = 'line_map' THEN em.string_value END) as line_map
                            FROM embeddings e
                            JOIN embedding_metadata em ON e.id = em.id
                            GROUP BY e.id
                            HAVING MAX(CASE WHEN em.key = 'type' THEN em.string_value END) = 'code'
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
                    
                    try:
                        raw_lmap = m.get("line_map", "{}")
                        lmap = json.loads(raw_lmap)
                    except Exception:
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
                
                return [types.TextContent(type="text", text="\n".join(lines))]
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return [types.TextContent(type="text", text=f"Error executing tool {name}: {str(e)}")]
    
    return app
