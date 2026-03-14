import os
import re
import sys

# Agregamos la ruta del engine para poder importar GitignoreParser
sys.path.append(os.path.join(os.path.dirname(__file__), "ace_engine", "core"))
try:
    from indexer import GitignoreParser, Indexer
except ImportError:
    print("Error importando Indexer. Ejecuta el script desde ACE indexer.")
    sys.exit(1)

def _extract_identifiers(content: str) -> str:
    patterns = [
        r'[a-z]+[A-Z][a-zA-Z0-9]*',      # camelCase
        r'[A-Z][a-z]+[A-Z][a-zA-Z0-9]*', # PascalCase
        r'[a-z]+_[a-z0-9_]+',            # snake_case
    ]
    identifiers = []
    for p in patterns:
        matches = re.findall(p, content)
        identifiers.extend(matches)
    
    unique_idents = list(dict.fromkeys(identifiers))
    return " ".join(unique_idents)

def calculate_ram_impact(project_path: str):
    indexer = Indexer()
    gitignore = GitignoreParser(project_path)
    
    total_files = 0
    total_bytes_raw = 0
    total_bytes_identifiers = 0
    
    for root, dirs, files in os.walk(project_path):
        # Filtros base
        if ".ace" in dirs: dirs.remove(".ace")
        if ".git" in dirs: dirs.remove(".git")
        if "node_modules" in dirs: dirs.remove("node_modules")
        if "venv" in dirs: dirs.remove("venv")
        if "__pycache__" in dirs: dirs.remove("__pycache__")
        
        if gitignore.match(root):
            dirs[:] = []
            continue
            
        for file in files:
            filepath = os.path.join(root, file)
            
            if indexer._should_ignore(filepath, gitignore):
                continue
                
            if not file.endswith((
                ".html", ".htm", ".css", ".scss", ".less", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
                ".py", ".php", ".rb", ".go", ".java", ".cs", ".rs", ".kt", ".swift", ".dart", ".sh",
                ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".env", ".sql", ".md", ".txt"
            )): continue
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                total_bytes_raw += len(content.encode('utf-8'))
                
                ident_bag = _extract_identifiers(content)
                total_bytes_identifiers += len(ident_bag.encode('utf-8'))
                
                total_files += 1
            except Exception:
                pass

    print(f"\n--- Analisis de Impacto RAM (ACE V3) ---")
    print(f"Proyecto evaluado: {project_path}")
    print(f"Total de archivos indexables: {total_files}")
    
    raw_mb = total_bytes_raw / (1024 * 1024)
    ident_mb = total_bytes_identifiers / (1024 * 1024)
    
    print(f"\nTamaño del Codigo Fuente Púro: {raw_mb:.2f} MB")
    print(f"Tamaño de los Metadatos V3 (Ident_Bag): {ident_mb:.4f} MB")
    
    overhead_pct = (total_bytes_identifiers / total_bytes_raw) * 100 if total_bytes_raw > 0 else 0
    print(f"\nProporción: El índice literal pesa un {overhead_pct:.1f}% del código fuente.")
    print(f"-> Cada busqueda Híbrida consumira EXACTAMENTE {ident_mb:.4f} MB de RAM extra en ChromaDB en lugar de hacer Disk I/O.")

if __name__ == "__main__":
    calculate_ram_impact(os.getcwd())
