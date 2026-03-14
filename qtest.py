import tree_sitter_python as tsp
import tree_sitter as ts

p = ts.Parser()
p.language = ts.Language(tsp.language())
code = b"class A(Base):\n  def x(self):\n    self.foo()\n"
t = p.parse(code)
q_call = ts.Query(p.language, "(call function: (attribute attribute: (identifier) @f))")

qc = ts.QueryCursor(q_call)
print("CAPTURES:")
print(qc.captures(t.root_node))
