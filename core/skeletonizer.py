import os
from tree_sitter import Language, Parser, Query, QueryCursor
import tree_sitter_python

try:
    import tree_sitter_javascript
    import tree_sitter_typescript
    import tree_sitter_php
    HAS_MULTI_LANG = True
except ImportError:
    HAS_MULTI_LANG = False

class Skeletonizer:
    def __init__(self):
        self.parsers_cache = {}
        self.queries_cache = {}
        
        self.LANG_REGISTRY = {
            '.py': lambda: Language(tree_sitter_python.language()),
        }
        if HAS_MULTI_LANG:
            self.LANG_REGISTRY['.js'] = lambda: Language(tree_sitter_javascript.language())
            self.LANG_REGISTRY['.jsx'] = lambda: Language(tree_sitter_javascript.language())
            self.LANG_REGISTRY['.ts'] = lambda: Language(tree_sitter_typescript.language_typescript())
            self.LANG_REGISTRY['.tsx'] = lambda: Language(tree_sitter_typescript.language_tsx())
            self.LANG_REGISTRY['.php'] = lambda: Language(tree_sitter_php.language_php())
            
        self.fallback_lang = self.LANG_REGISTRY['.py']()
        
        # AST Queries to extract function calls
        self.CALL_QUERIES_STR = {
            '.py': "(call function: (identifier) @func_name) (call function: (attribute attribute: (identifier) @func_name))",
            '.js': "(call_expression function: (identifier) @func_name) (call_expression function: (member_expression property: (property_identifier) @func_name))",
            '.ts': "(call_expression function: (identifier) @func_name) (call_expression function: (member_expression property: (property_identifier) @func_name))",
            '.tsx': "(call_expression function: (identifier) @func_name) (call_expression function: (member_expression property: (property_identifier) @func_name))",
            '.php': "(function_call_expression function: (name) @func_name) (member_call_expression name: (name) @func_name)",
        }
        
        # AST Queries to extract inheritance (class bases)
        self.INHERIT_QUERIES_STR = {
            '.py': "(class_definition superclasses: (argument_list (identifier) @base_class))",
            '.js': "(class_definition heritage: (extends_clause (identifier) @base_class))",
            '.ts': "(class_definition heritage: (extends_clause (identifier) @base_class))",
            '.tsx': "(class_definition heritage: (extends_clause (identifier) @base_class))",
            '.php': "(base_clause (name) @base_class)",
        }

    def _get_parser_and_query(self, filepath: str):
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in self.LANG_REGISTRY:
            ext = '.py' # fallback
            
        if ext not in self.parsers_cache:
            lang = self.LANG_REGISTRY[ext]()
            p = Parser()
            p.language = lang
            self.parsers_cache[ext] = p
            
            query_str = self.CALL_QUERIES_STR.get(ext, "")
            try:
                self.queries_cache[ext] = Query(lang, query_str) if query_str else None
            except Exception:
                self.queries_cache[ext] = None
            
            inherit_str = self.INHERIT_QUERIES_STR.get(ext, "")
            try:
                self.queries_cache[ext + "_inherit"] = Query(lang, inherit_str) if inherit_str else None
            except Exception:
                self.queries_cache[ext + "_inherit"] = None
            
        return self.parsers_cache[ext], self.queries_cache[ext], self.queries_cache.get(ext + "_inherit")

    def skeletonize(self, code: str, filepath: str = "") -> tuple[str, dict, list, list]:
        """
        [v0.9.0] Full AST-based skeleton extraction.
        Uses tree-sitter to traverse the parse tree, extracting only structural
        nodes (imports, class/function signatures). This is immune to false
        positives from strings and comments that contain 'def' or 'class'.
        Returns (skeleton_str, line_map) where line_map = {"symbol_name": 1based_line}
        """
        try:
            parser, call_query, inherit_query = self._get_parser_and_query(filepath)
            tree = parser.parse(bytes(code, "utf8"))
            lines = code.splitlines()
            skeleton_lines = []
            line_map = {}  # {"real_function": 3, "RealClass": 5}
            calls_found = []

            if call_query:
                try:
                    cursor = QueryCursor(call_query)
                    captures = cursor.captures(tree.root_node)
                    if isinstance(captures, dict):
                        for nodes in captures.values():
                            for node in nodes:
                                calls_found.append(node.text.decode("utf8"))
                    else:
                        for node, _ in captures:
                            calls_found.append(node.text.decode("utf8"))
                except Exception as e:
                    print(f"[DEBUG AST CALLS] error: {e}")
            
            # Deduplicate calls to save space
            calls_found = list(dict.fromkeys(calls_found))
            
            inherits_found = []
            if inherit_query:
                try:
                    cursor = QueryCursor(inherit_query)
                    captures = cursor.captures(tree.root_node)
                    if isinstance(captures, dict):
                        for nodes in captures.values():
                            for node in nodes:
                                inherits_found.append(node.text.decode("utf8"))
                    else:
                        for node, _ in captures:
                            inherits_found.append(node.text.decode("utf8"))
                except Exception as e:
                    print(f"[DEBUG AST INHERITS] error: {e}")
            inherits_found = list(dict.fromkeys(inherits_found))

            def _traverse(node):
                # Capture import nodes
                if node.type in ("import_statement", "import_from_statement"):
                    start = node.start_point[0]
                    skeleton_lines.append(lines[start])
                    # Extract module name (e.g. "import os" -> "os")
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        line_map[name_node.text.decode("utf8")] = start + 1

                # Capture class/function definitions (including JS/TS standard declarations)
                elif node.type in ("function_definition", "async_function_definition", "class_definition", "function_declaration", "generator_function_declaration", "method_definition", "class_declaration", "method_declaration"):
                    start = node.start_point[0]
                    # Register name -> line (base-1 for LOCATION)
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        line_map[name_node.text.decode("utf8")] = start + 1
                    
                    # Add signature to skeleton
                    for i in range(start, min(start + 10, len(lines))):
                        skeleton_lines.append(lines[i])
                        if lines[i].rstrip().endswith(":"):
                            indent = len(lines[i]) - len(lines[i].lstrip())
                            skeleton_lines.append(" " * (indent + 4) + "...")
                            break
                    
                    if node.type in ("class_definition", "class_declaration"):
                        # Descend into classes to catch methods
                        pass 
                    else:
                        # For functions, stop here to avoid capturing local variables/internal logic in skeleton
                        return 

                # Extracción Especial para Variables JS/TS y CommonJS Exports
                elif node.type in ("lexical_declaration", "variable_declaration", "expression_statement"):
                    has_function = False
                    start = node.start_point[0]
                    
                    if node.type in ("lexical_declaration", "variable_declaration"):
                        for child in node.children:
                            if child.type == "variable_declarator":
                                value_node = child.child_by_field_name("value")
                                if value_node and value_node.type in ("arrow_function", "function", "function_expression", "async_function_expression"):
                                    name_node = child.child_by_field_name("name")
                                    if name_node:
                                        line_map[name_node.text.decode("utf8")] = start + 1
                                        has_function = True
                    
                    elif node.type == "expression_statement":
                        for child in node.children:
                            if child.type == "assignment_expression":
                                left = child.child_by_field_name("left")
                                right = child.child_by_field_name("right")
                                
                                if left and right and right.type in ("arrow_function", "function_expression", "async_function_expression"):
                                    if left.type == "member_expression":
                                        prop = left.child_by_field_name("property")
                                        if prop:
                                            line_map[prop.text.decode("utf8")] = start + 1
                                            has_function = True
                                elif left and right and right.type == "object":
                                    # Handle module.exports = { ... }
                                    for pair in right.children:
                                        if pair.type == "pair":
                                            k = pair.child_by_field_name("key")
                                            v = pair.child_by_field_name("value")
                                            if k and v and v.type in ("arrow_function", "function_expression", "async_function_expression"):
                                                line_map[k.text.decode("utf8")] = pair.start_point[0] + 1
                                                has_function = True

                    if has_function:
                        skeleton_lines.append(lines[start])
                        curr = start
                        found_block = False
                        while curr < min(start + 5, len(lines)):
                            if "{" in lines[curr]:
                                if curr > start: skeleton_lines.append(lines[curr])
                                found_block = True
                                break
                            curr += 1
                        if found_block:
                            indent = len(lines[curr]) - len(lines[curr].lstrip())
                            skeleton_lines.append(" " * (indent + 4) + "...")
                        return

                # Recurse into children
                for child in node.children:
                    _traverse(child)

            _traverse(tree.root_node)
            return "\n".join(skeleton_lines), line_map, calls_found, inherits_found

        except Exception as e:
            import sys, traceback
            error_log = os.path.join(os.path.dirname(__file__), 'skeletonizer_error.log')
            with open(error_log, 'a') as ef:
                ef.write(f"[Skeletonizer] Error for {filepath}:\n")
                traceback.print_exc(file=ef)
                
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
            return "\n".join(skeleton_lines), {}, [], []

    def scan_blind_spots(self, code: str, filepath: str):
        """
        Scans a file for 'blind spots' or anti-patterns that often lead to silent errors.
        Returns a list of diagnostic messages with line numbers.
        """
        diagnostics = []
        try:
            language = self._get_language(filepath)
            print(f"[DEBUG scan_blind_spots] filepath: {filepath}, language: {language}")
            if not language:
                return []

            ext = os.path.splitext(filepath)[1].lower()
            lang_obj = self.LANG_REGISTRY.get(ext, self.LANG_REGISTRY['.py'])()
            parser = Parser(lang_obj)
            tree = parser.parse(bytes(code, "utf8"))
            lines = code.splitlines()

            # Define patterns for blind spots
            # 1. Python patterns
            if language == "python":
                query_str = "(except_clause (block (pass_statement)) @bare_except_pass) (except_clause (block (expression_statement (string))) @bare_except_doc)"
                query = Query(lang_obj, query_str)
                cursor = QueryCursor(query)
                captures = cursor.captures(tree.root_node)
                for tag, nodes in captures.items():
                    for node in nodes:
                        msg = "Found 'except: pass' or empty bare except. This swallows errors silently."
                        if tag == "bare_except_doc":
                            msg = "Found except with only a docstring/string. Likely swallows errors silently."
                        diagnostics.append({
                            "line": node.start_point[0] + 1,
                            "type": tag,
                            "message": msg
                        })

            # 2. Javascript / Typescript patterns
            elif language in ("javascript", "typescript"):
                query_str = "(catch_clause body: (statement_block) @catch_body)"
                query = Query(lang_obj, query_str)
                cursor = QueryCursor(query)
                captures = cursor.captures(tree.root_node)
                for tag, nodes in captures.items():
                    for node in nodes:
                        # Post-process: check if body is empty or just comments
                        body_code = node.text.decode("utf8").strip()
                        inner = body_code[1:-1].strip()
                        if not inner or len(inner) < 3:
                             diagnostics.append({
                                "line": node.start_point[0] + 1,
                                "type": "silent_catch",
                                "message": "Catch block is empty or contains no functional code. Potential silent error."
                            })
            
            return diagnostics
        except Exception:
            return []

    def _get_language(self, filepath: str):
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".py": return "python"
        if ext in (".js", ".jsx"): return "javascript"
        if ext in (".ts", ".tsx"): return "typescript"
        if ext == ".go": return "go"
        return None

# Update the main skeletonize return to include inherits_found
