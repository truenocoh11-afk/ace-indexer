import time
import re
from typing import List, Dict

# Simulación de la base de datos (ChromaDB)
# En ChromaDB, metadatas es una lista de diccionarios.
MOCK_CHROMA_METADATA = []
MOCK_CHROMA_IDS = []

# Corpus de prueba (Simulando 10,000 archivos para estrés)
NUM_FILES = 10000

def _extract_identifiers(content: str) -> str:
    # Extrae camelCase, PascalCase, snake_case
    patterns = [
        r'[a-z]+[A-Z][a-zA-Z0-9]*',
        r'[A-Z][a-z]+[A-Z][a-zA-Z0-9]*',
        r'[a-z]+_[a-z0-9_]+',
    ]
    identifiers = []
    for p in patterns:
        matches = re.findall(p, content)
        identifiers.extend(matches)
    
    # Deduplicate and join as space-separated string (for metadata storage)
    unique_idents = list(dict.fromkeys(identifiers))
    return " ".join(unique_idents)

def setup_mock_db():
    print(f"Indexando {NUM_FILES} archivos simulados...")
    start_time = time.time()
    
    for i in range(NUM_FILES):
        file_path = f"project/src/module_{i}.py"
        content = f"def my_function_{i}(user_data):\n    class_name = StateManager{i}\n    return user_data.process()"
        
        # En la V3, ACE extrae esto en la indexación
        ident_bag = _extract_identifiers(content)
        
        MOCK_CHROMA_IDS.append(file_path)
        MOCK_CHROMA_METADATA.append({
            "path": file_path,
            "ident_bag": ident_bag # <--- LA MAGIA ESTÁ AQUÍ
        })
        
    print(f"Indexación completada en {(time.time() - start_time)*1000:.2f}ms")

# --- COMPARATIVAS DE BÚSQUEDA ---

def search_v2_legacy(query_identifiers: List[str], top_k_ids: List[str]):
    """Simula lo que hace ACE hoy: abrir archivos del disco"""
    scores = {file_id: 0.0 for file_id in top_k_ids}
    
    for file_id in top_k_ids:
        # Simulamos abrir el archivo y leerlo (I/O)
        # Un SSD NVMe rápido podría tomar ~0.1ms por lectura chica, agregamos sleep para simular disco
        time.sleep(0.0001) 
        
        # Simulamos encontrar las IDs
        if "my_function_500" in query_identifiers and file_id == "project/src/module_500.py":
            scores[file_id] += 15.0
            
    return scores

def search_v3_zvec_style(query_identifiers: List[str], top_k_ids: List[str], metadatas: List[Dict]):
    """Simula la propuesta V3: leer de metadata en RAM"""
    scores = {file_id: 0.0 for file_id in top_k_ids}
    
    for i, file_id in enumerate(top_k_ids):
        # Acceso 100% en RAM
        ident_bag = metadatas[i].get("ident_bag", "")
        
        hits = 0
        for q_id in query_identifiers:
            if q_id in ident_bag: # Fast string matching
                hits += 1
                
        scores[file_id] += (hits * 0.5) # Simulación de WeightedScore
        
    return scores


if __name__ == "__main__":
    setup_mock_db()
    
    # Asumimos que Chroma (semántica) ya nos devolvió los top 50 archivos más relevantes
    top_50_ids = MOCK_CHROMA_IDS[:50]
    top_50_metadatas = MOCK_CHROMA_METADATA[:50]
    
    query = ["my_function_25", "StateManager25", "user_data"]
    
    print("\n--- Ejecutando ACE v0.6.4 (Legacy Disk I/O) ---")
    t0 = time.time()
    scores_v2 = search_v2_legacy(query, top_50_ids)
    t_v2 = (time.time() - t0) * 1000
    print(f"Tiempo: {t_v2:.2f}ms")
    
    print("\n--- Ejecutando ACE V3 (In-RAM Metadata Sparse Vector) ---")
    t0 = time.time()
    scores_v3 = search_v3_zvec_style(query, top_50_ids, top_50_metadatas)
    t_v3 = (time.time() - t0) * 1000
    print(f"Tiempo: {t_v3:.2f}ms")
    
    # Evitar division por 0 si es demasiado rapido
    t_v3_safe = max(0.001, t_v3)
    print(f"\n🚀 Aceleración esperada: {t_v2 / t_v3_safe:.0f}x más rápido")
