import os
from pathlib import Path

class MemoryManager:
    """Gestiona la memoria persistente de un proyecto."""
    
    MEMORY_FILES = {
        "context": "project_context.md",
        "task": "active_task.md", 
        "lessons": "lessons_learned.md"
    }

    TEMPLATES = {
        "context": "# Project Context\n\n<!-- Sin contenido aún. Describe el Stack, Misión y Arquitectura aquí. -->",
        "task": "# Active Task\n\n<!-- Sin tarea activa registrada. -->",
        "lessons": "# Lessons Learned\n\n<!-- Sin lecciones registradas. -->"
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
                filepath.write_text(self.TEMPLATES[key], encoding="utf-8")
    
    def read(self, memory_type: str = "all") -> str:
        """Lee uno o todos los archivos de memoria."""
        self.ensure_structure()
        
        if memory_type == "all":
            content = []
            uninitialized = []
            
            # Order them logically
            keys = ["context", "task", "lessons"]
            for key in keys:
                filename = self.MEMORY_FILES[key]
                filepath = self.memory_dir / filename
                
                if filepath.exists():
                    text = filepath.read_text(encoding='utf-8').strip()
                    # Check if it's just the template
                    if text == self.TEMPLATES[key].strip():
                        uninitialized.append(key)
                    
                    content.append(f"## {key.upper()}\n{text}")
            
            result = "\n\n---\n\n".join(content)
            
            # Smart Detection: If Context is empty, prompt the agent
            if "context" in uninitialized:
                result += "\n\n🚨 [SYSTEM NOTICE] MEMORY DETECTED UNINITIALIZED CONTEXT"
                result += "\nThis looks like an existing project with empty memory."
                result += "\n👉 ACTION REQUIRED: Analyze file structure, `README.md` or config files and call `ace_update_memory('context', ...)`."
            else:
                # Health Check: Even if context exists, verify it has infrastructure info
                context_text = ""
                for item in content:
                    if item.startswith("## CONTEXT"):
                        context_text = item.lower()
                        break
                
                infra_keywords = ["ssh", "port", "vps", "server", "deploy", "pm2", "docker"]
                has_infra = any(kw in context_text for kw in infra_keywords)
                
                if not has_infra and len(context_text) > 50:  # Only warn if context has some content
                    result += "\n\n⚠️ [HEALTH CHECK] Context may be missing infrastructure info."
                    result += "\n   If this project uses VPS/SSH, ensure `context` contains: Access, Ports, Paths, Commands."
                
            return result

        else:
            # ... (single file logic could also check, but 'all' is the main boot entry)
            filename = self.MEMORY_FILES.get(memory_type)
            if not filename:
                return f"[ERROR] Tipo '{memory_type}' no soportado. Usa: {list(self.MEMORY_FILES.keys())}"
                
            filepath = self.memory_dir / filename
            if filepath.exists():
                return filepath.read_text(encoding="utf-8")
            return f"[ERROR] Archivo para '{memory_type}' no encontrado."
    
    def write(self, memory_type: str, content: str, append: bool = True, force: bool = False, archive_legacy: bool = False):
        """Escribe en un archivo de memoria."""
        self.ensure_structure()
        filename = self.MEMORY_FILES.get(memory_type)
        if not filename:
            return f"[ERROR] Tipo '{memory_type}' no soportado."
            
        filepath = self.memory_dir / filename
        
        # Security Check: Smart Overwrite with optional Legacy Preservation
        if filepath.exists():
            existing_content = filepath.read_text(encoding="utf-8").strip()
            template_content = self.TEMPLATES.get(memory_type, "").strip()
            
            if existing_content and existing_content != template_content:
                if archive_legacy:
                    # Move old context to legacy
                    import datetime
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    new_full_content = (
                        f"{content}\n\n"
                        f"---\n\n"
                        f"## 🗄️ Legacy {memory_type.capitalize()} (Archived on {timestamp})\n"
                        f"> This content was preserved to avoid confusion with new context.\n\n"
                        f"{existing_content}"
                    )
                    
                    try:
                        filepath.write_text(new_full_content + "\n", encoding="utf-8")
                        msg = f"[WARN-OK] Escrito en {memory_type}. El contenido anterior fue convertido a 'Legacy'."
                        if memory_type in ["context", "task"]:
                            msg += "\n\n💡 SELF-CHECK: Revisa si el contenido heredado (Legacy) ya no es necesario; podrás borrarlo usando force=True en tu próxima escritura si así lo deseas."
                        return msg
                    except Exception as e:
                        return f"[ERROR] Falló la escritura con preservación legacy: {str(e)}"
                elif not append and not force:
                    return f"[SECURITY ERROR] Attempted to overwrite existing '{memory_type}'. By default you must append (append=True). If old context is contradictory, use archive_legacy=True to archive it. To completely wipe it, use force=True."

        mode = "a" if append else "w"

        
        try:
            with open(filepath, mode, encoding="utf-8") as f:
                if append:
                    f.write("\n")
                f.write(content + "\n")
            msg = f"[OK] Escrito en {memory_type}"
            if memory_type in ["context", "task"]:
                msg += "\n\n💡 SELF-CHECK: ¿La información registrada permite a un agente sin historial operar este proyecto?"
            return msg
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
