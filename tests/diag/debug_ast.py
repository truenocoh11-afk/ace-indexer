from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import os

PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)

code = """
def bad():
    try:
        x = 1/0
    except:
        pass
"""

tree = parser.parse(bytes(code, "utf8"))

def print_node(node, indent=0):
    print("  " * indent + f"{node.type} [{node.start_point} - {node.end_point}]")
    if node.child_count > 0:
        for child in node.children:
            print_node(child, indent + 1)

print_node(tree.root_node)

query_str = """
(except_clause
    (block
        (pass_statement)) @bare_pass)
"""
query = PY_LANGUAGE.query(query_str)
print(f"\nQuery attributes: {dir(query)}")
# Try different ways
try:
    captures = query.captures(tree.root_node)
    print(f"\nCaptures (query.captures): {captures}")
except Exception as e:
    print(f"query.captures failed: {e}")
