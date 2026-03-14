"""
Markov Chain Call Graph - Fase 3 (P4)
Construye un grafo de transición caller→callee desde la metadata 'calls' de ChromaDB.
"""
import json
import os
from collections import defaultdict

class MarkovCallGraph:
    def __init__(self):
        # {caller_file: {callee_func: count}}
        self.transitions = defaultdict(lambda: defaultdict(int))

    def ingest_chroma_metadata(self, metadatas: list):
        """Alimenta el grafo desde una lista de metadatas de ChromaDB."""
        for meta in metadatas:
            if not meta: continue
            source_file = meta.get("path", "unknown")
            calls_raw = meta.get("calls", "[]")
            try:
                calls = json.loads(calls_raw) if isinstance(calls_raw, str) else (calls_raw or [])
            except Exception:
                calls = []
            
            if not isinstance(calls, list):
                calls = []
                
            for callee in calls:
                self.transitions[source_file][callee] += 1

    def get_top_callees(self, source_file: str, top_n: int = 10) -> list[tuple]:
        """Retorna las N funciones más llamadas desde source_file."""
        counts = self.transitions.get(source_file, {})
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]

    def get_call_probability(self, source_file: str, callee: str) -> float:
        """Probabilidad de que source_file llame a callee."""
        counts = self.transitions.get(source_file, {})
        total = sum(counts.values())
        if total == 0:
            return 0.0
        return counts.get(callee, 0) / total

    def to_mermaid(self, max_edges: int = 20) -> str:
        """Genera un diagrama Mermaid del grafo de llamadas."""
        lines = ["graph LR"]
        edges = 0
        for source, callees in self.transitions.items():
            src_label = os.path.basename(source)
            for callee, count in sorted(callees.items(), key=lambda x: x[1], reverse=True)[:3]:
                lines.append(f'    {src_label} -->|"{callee}({count}x)"| {callee}')
                edges += 1
                if edges >= max_edges:
                    break
            if edges >= max_edges:
                break
        return "\n".join(lines)
