from tree_sitter import Language, Parser
import tree_sitter_python as tspython

PY_LANGUAGE = Language(tspython.language())
parser = Parser()
parser.language = PY_LANGUAGE

code = """
def bad():
    try:
        x = 1/0
    except:
        pass
"""

tree = parser.parse(bytes(code, "utf8"))

def print_node(node, indent=0):
    text = node.text.decode('utf8').replace('\n', '\\n')[:30]
    print("  " * indent + f"{node.type} [{node.start_point}]: '{text}'")
    for child in node.children:
        print_node(child, indent + 1)

print_node(tree.root_node)
