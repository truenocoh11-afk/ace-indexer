import sys
from pathlib import Path
sys.path.append(str(Path("ace_engine").absolute()))
from core.memory import MemoryManager

def update_real_memory():
    project_path = "C:\\Users\\Julian\\Documents\\BoluIdeas\\ACE indexer"
    manager = MemoryManager(project_path)
    
    # 1. Real Project Context
    context = """# ACE Indexer - Project Context

## Identidad
- **Nombre**: ACE (Antigravity Context Engine)
- **Versión**: v0.6.4
- **Misión**: Proveer memoria de largo plazo y búsqueda semántica avanzada para agentes de IA.

## Stack Tecnológico
- **Lenguaje**: Python 3.10+
- **Core**: ChromaDB (Vector Store), SentenceTransformers (Embeddings)
- **Interface**: MCP (Model Context Protocol)
- **Arquitectura**: 
    - `ace_engine/core`: Lógica de indexación y memoria.
    - `ace_engine/adapters`: Servidor MCP.

## Componentes Clave
1. **Indexer**: Búsqueda híbrida (Regex + Semántica).
2. **MemoryManager**: Gestión de archivos Markdown persistentes (`.ace/memory/`).
3. **Declaration Boost**: Algoritmo de priorización de definiciones de código.
"""
    manager.write("context", context)
    
    # 2. Real Active Task
    task = """# Tarea Actual

## Objetivo
- Implementar y estabilizar el protocolo **ACE Memory**.
- Automatizar la actualización de memoria ante eventos de despliegue (Git, SSH, Deploy).

## Estado
- [x] Core Memory Logic (`memory.py`)
- [x] MCP Tools (`ace_boot_memory`)
- [x] Git Integration (Commit inicial)
- [ ] Automation Hooks (En diseño)
"""
    manager.write("task", task)
    
    # 3. Clean Lessons (optional, keep empty or init)
    lessons = """# Lecciones Aprendidas

- **Git en Subdirectorios**: Si el repo git no está en la raíz, los comandos fallan. Siempre verificar `gi rev-parse --show-toplevel`.
- **MCP Reload**: `uvx` cachea agresivamente. Al cambiar código local, es mejor apuntar `mcp_config.json` al path local o forzar reinstalación.
- **Windows PowerShell**: El operador `&&` no existe en versiones viejas. Usar `;`.
"""
    manager.write("lessons", lessons)

    print("✅ Memory Updated with REAL context.")

if __name__ == "__main__":
    update_real_memory()
