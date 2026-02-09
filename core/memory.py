import os
from pathlib import Path

class MemoryManager:
    """Gestiona la memoria persistente de un proyecto."""
    
    MEMORY_FILES = {
        "context": "project_context.md",
        "task": "active_task.md", 
        "lessons": "lessons_learned.md"
    }
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.memory_dir = self.project_path / ".ace" / "memory"
    
    def ensure_structure(self):
        """Crea la carpeta memory si no existe."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        for key, filename in self.MEMORY_FILES.items():
            filepath = self.memory_dir / filename
            if not filepath.exists():
                filepath.write_text(f"# {key.title()}\n\n<!-- Sin contenido aún -->", encoding="utf-8")
    
    def read(self, memory_type: str = "all") -> str:
        """Lee uno o todos los archivos de memoria."""
        self.ensure_structure()
        if memory_type == "all":
            content = []
            # Order them logically
            keys = ["context", "task", "lessons"]
            for key in keys:
                filename = self.MEMORY_FILES[key]
                filepath = self.memory_dir / filename
                if filepath.exists():
                    content.append(f"## {key.upper()}\n{filepath.read_text(encoding='utf-8')}")
            return "\n\n---\n\n".join(content)
        else:
            filename = self.MEMORY_FILES.get(memory_type)
            if not filename:
                return f"[ERROR] Tipo '{memory_type}' no soportado. Usa: {list(self.MEMORY_FILES.keys())}"
                
            filepath = self.memory_dir / filename
            if filepath.exists():
                return filepath.read_text(encoding="utf-8")
            return f"[ERROR] Archivo para '{memory_type}' no encontrado."
    
    def write(self, memory_type: str, content: str, append: bool = False):
        """Escribe en un archivo de memoria."""
        self.ensure_structure()
        filename = self.MEMORY_FILES.get(memory_type)
        if not filename:
            return f"[ERROR] Tipo '{memory_type}' no soportado."
            
        filepath = self.memory_dir / filename
        mode = "a" if append else "w"
        
        try:
            with open(filepath, mode, encoding="utf-8") as f:
                if append:
                    f.write("\n")
                f.write(content + "\n")
            return f"[OK] Escrito en {memory_type}"
        except Exception as e:
            return f"[ERROR] Falló la escritura: {str(e)}"

    def has_booted(self) -> bool:
        """Verifica si ya se realizó el boot en esta sesión (vía flag temporal)."""
        # Nota: Usamos un archivo .booted dentro de .ace/memory para persistencia de sesión local
        # Se debería limpiar manualmente si se quiere forzar un nuevo boot
        flag = self.memory_dir / ".booted"
        return flag.exists()

    def set_booted(self):
        """Marca la sesión como booteada."""
        self.ensure_structure()
        (self.memory_dir / ".booted").touch()

    def clear_boot_flag(self):
        """Limpia el flag de boot."""
        flag = self.memory_dir / ".booted"
        if flag.exists():
            flag.unlink()
