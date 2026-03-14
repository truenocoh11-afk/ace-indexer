import sys
from tree_sitter import Language, Parser
import tree_sitter_javascript

lang = Language(tree_sitter_javascript.language())
parser = Parser()
parser.language = lang

js_code = b"""
const getPb1 = async () => { return 1; };
const getPb2 = function() { return 2; };
let getPb3 = () => {};
var getPb4 = function() {};

exports.getPb5 = function() { return 5; };
module.exports.getPb6 = () => 6;
module.exports = {
    getPb7: function() {},
    getPb8: () => {}
};

function normalFunction() {}
class NormalClass { method() {} }
"""

tree = parser.parse(js_code)

def print_tree(node, depth=0):
    print("  " * depth + f"{node.type} [{node.start_point[0]}:{node.start_point[1]} - {node.end_point[0]}:{node.end_point[1]}]")
    if node.is_named and node.type == 'identifier':
        print("  " * depth + f"  name: {node.text.decode('utf-8')}")
    if node.type == 'property_identifier':
        print("  " * depth + f"  prop: {node.text.decode('utf-8')}")
    for child in node.children:
        print_tree(child, depth + 1)

print_tree(tree.root_node)
