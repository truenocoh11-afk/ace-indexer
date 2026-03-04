
import sys
import os
import json
from pathlib import Path

# Add core path
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir))

from core.indexer import Indexer

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
        # CONF logic
        conf = "HIGH" if literal and rrf_score > 0.7 else ("MED" if literal or rrf_score > 0.4 else "LOW")
        snippet_len = min(len(doc), 600)
        lines.append(f"{rel_path}\tcode\t{flags_str}\t{conf}\t{location}\t{snippet_len}")

    return "\n".join(lines)

def test_compact_output_format():
    print("\n--- Testing Compact Output Format (CONF column & Telemetry) ---")
    project_path = str(Path(current_dir).parent)
    indexer = Indexer()
    
    # 1. Search for "Indexer" to match the class name and trigger line_map lookup
    query = "Indexer"
    print(f"Querying: '{query}' in {project_path}")
    
    # workspace_only=True is the default we want to test
    results = indexer.query(project_path, query, workspace_only=True)
    
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    if not documents:
        print("❌ No results found! Cannot verify format.")
        return

    # 2. Format compact
    formatted = _format_compact(documents, metadatas, query, project_path)
    
    print("\n[Compact Output Start]")
    print(formatted)
    print("[Compact Output End]\n")
    
    # 3. Verification
    if "CONF" in formatted and "FILE\tTYPE\tFLAGS\tCONF\tLOCATION" in formatted:
        print("✅ CONF column found in header")
    else:
        print("❌ CONF column MISSING in header")
        
    if "[FORMAT v1.1]" in formatted:
        print("✅ [FORMAT v1.1] tag found")
    else:
        print("❌ [FORMAT v1.1] tag MISSING")
        
    # Check if LOCATION is resolved (e.g., L14 or similar, not just -)
    # We expect 'Indexer' to match the class definition in indexer.py, so it should have a line number if line_map works
    # Or at least L<something>
    if "\tL" in formatted:
        print("✅ LOCATION resolved (found 'L...')")
    else:
        print("⚠️ LOCATION might be '-' (Check if line_map is working)")

    # Check for CONF values
    if "HIGH" in formatted or "MED" in formatted or "LOW" in formatted:
         print("✅ CONF values populated")
    else:
         print("❌ CONF values MISSING")

if __name__ == "__main__":
    test_compact_output_format()
