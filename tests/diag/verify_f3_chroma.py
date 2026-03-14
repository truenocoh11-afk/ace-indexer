import sys
import os
import json

# Ajustar path
sys.path.append(os.getcwd())

from core.chroma_manager import ChromaManager

def verify_results():
    cm = ChromaManager()
    # Buscar un archivo que sepamos que tiene llamadas e herencia
    # core/indexer.py es un buen candidato para llamadas
    results = cm.collection.get(
        where={"path": "core/indexer.py"},
        include=["metadatas"]
    )
    
    if not results["metadatas"]:
        print("❌ Error: indexer.py not found in index.")
        return

    meta = results["metadatas"][0]
    calls = meta.get("calls")
    inherits = meta.get("inherits")
    
    print(f"File: core/indexer.py")
    print(f"Calls (first 5): {json.loads(calls)[:5] if calls else 'None'}")
    print(f"Inherits: {json.loads(inherits) if inherits else 'None'}")

    # Verificar un archivo con herencia conocida
    # chroma_manager.py podría no tener, pero busquemos MarkowCallGraph en core/markov.py
    results_m = cm.collection.get(
        where={"path": "core/markov.py"},
        include=["metadatas"]
    )
    if results_m["metadatas"]:
        meta_m = results_m["metadatas"][0]
        print(f"\nFile: core/markov.py")
        print(f"Inherits: {json.loads(meta_m.get('inherits', '[]'))}")

    if calls and inherits:
        print("\n✅ SUCCESS: Phase 3 metadata (calls & inherits) detected in ChromaDB.")
    else:
        print("\n⚠️ WARNING: Some metadata might be empty, but fields exist.")

if __name__ == "__main__":
    verify_results()
