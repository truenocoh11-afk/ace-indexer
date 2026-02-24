import os
from tree_sitter import Language, Parser
import tree_sitter_python

class Skeletonizer:
    def __init__(self):
        # In a real setup, we might need to compile languages or use pre-built bindings
        # For simplicity in this "portable" version, we rely on the python bindings
        self.PY_LANGUAGE = Language(tree_sitter_python.language())
        self.parser = Parser()
        self.parser.language = self.PY_LANGUAGE

    def skeletonize(self, code: str) -> tuple[str, dict]:
        """
        [v0.9.0] Full AST-based skeleton extraction.
        Uses tree-sitter to traverse the parse tree, extracting only structural
        nodes (imports, class/function signatures). This is immune to false
        positives from strings and comments that contain 'def' or 'class'.
        Returns (skeleton_str, line_map) where line_map = {"symbol_name": 1based_line}
        """
        try:
            tree = self.parser.parse(bytes(code, "utf8"))
            lines = code.splitlines()
            skeleton_lines = []
            line_map = {}  # {"real_function": 3, "RealClass": 5}

            def _traverse(node):
                # Capture import nodes
                if node.type in ("import_statement", "import_from_statement"):
                    start = node.start_point[0]
                    skeleton_lines.append(lines[start])
                    # Extract module name (e.g. "import os" -> "os")
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        line_map[name_node.text.decode("utf8")] = start + 1

                # Capture class/function definitions (signature only, not body)
                elif node.type in ("function_definition", "async_function_definition", "class_definition"):
                    start = node.start_point[0]
                    # Register name -> line (base-1 for LOCATION)
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        line_map[name_node.text.decode("utf8")] = start + 1
                    # Find the colon marking end of signature line
                    for i in range(start, min(start + 10, len(lines))):
                        skeleton_lines.append(lines[i])
                        if lines[i].rstrip().endswith(":"):
                            indent = len(lines[i]) - len(lines[i].lstrip())
                            skeleton_lines.append(" " * (indent + 4) + "...")
                            break
                    return  # Do NOT descend into body; only top-level signature needed

                # Recurse into children for all other nodes
                for child in node.children:
                    _traverse(child)

            _traverse(tree.root_node)
            return "\n".join(skeleton_lines), line_map

        except Exception:
            # Fallback: safe naive line scan if tree-sitter fails for non-Python files
            lines = code.splitlines()
            skeleton_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(("import ", "from ", "class ", "def ", "async def ")):
                    skeleton_lines.append(line)
                    if ":" in line:
                        indent = len(line) - len(line.lstrip())
                        skeleton_lines.append(" " * (indent + 4) + "...")
            return "\n".join(skeleton_lines), {}
