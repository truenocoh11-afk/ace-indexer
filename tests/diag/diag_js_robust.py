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

def extract_symbols(node):
    line_map = {}
    
    def traverse(n):
        if n.type in ("function_declaration", "generator_function_declaration", "method_definition", "class_declaration"):
            # Find identifier
            for child in n.children:
                if child.type in ("identifier", "property_identifier"):
                    line_map[child.text.decode('utf8')] = n.start_point[0] + 1
                    break
        
        elif n.type in ("lexical_declaration", "variable_declaration"):
            for child in n.children:
                if child.type == "variable_declarator":
                    ident = None
                    is_func = False
                    for gc in child.children:
                        if gc.type == "identifier":
                            ident = gc.text.decode('utf8')
                        elif gc.type in ("arrow_function", "function_expression"):
                            is_func = True
                    if ident and is_func:
                        line_map[ident] = n.start_point[0] + 1
                        
        elif n.type == "expression_statement":
            for child in n.children:
                if child.type == "assignment_expression":
                    # Look for exports.foo = function()
                    left = None
                    right = None
                    for gc in child.children:
                        if gc.type == "member_expression":
                            left = gc
                        elif gc.type in ("arrow_function", "function_expression"):
                            right = gc
                    
                    if left and right:
                        # Extract the property name (rightmost identifier)
                        prop_names = [c for c in left.children if c.type == "property_identifier"]
                        if prop_names:
                            line_map[prop_names[-1].text.decode('utf8')] = n.start_point[0] + 1
                            
                    # What if right is an object literal? module.exports = { foo: function() }
                    for gc in child.children:
                        if gc.type == "object":
                            for pair in gc.children:
                                if pair.type == "pair":
                                    key = pair.child_by_field_name("key")
                                    value = pair.child_by_field_name("value")
                                    if key and value and value.type in ("arrow_function", "function_expression"):
                                        line_map[key.text.decode('utf8')] = pair.start_point[0] + 1
                                        
        for child in n.children:
            if n.type not in ("function_declaration", "arrow_function", "function_expression", "method_definition"):
                traverse(child)

    traverse(tree.root_node)
    return line_map

symbols = extract_symbols(tree.root_node)
print("EXTRACTED SYMBOLS:")
for k, v in symbols.items():
    print(f"  {k}: {v}")
