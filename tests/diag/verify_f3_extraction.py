import sys
import os

# Ajustar path para importar core
sys.path.append(os.getcwd())

from core.skeletonizer import Skeletonizer

def test_f3_extraction():
    skel = Skeletonizer()
    
    py_code = """
class Base:
    def greet(self):
        print("hello")

class Sub(Base):
    def work(self):
        self.greet()
        other_func()
"""
    skeleton, line_map, calls, inherits = skel.skeletonize(py_code, "test.py")
    
    print(f"Skeleton length: {len(skeleton)}")
    print(f"Line map: {line_map}")
    print(f"Calls: {calls}")
    print(f"Inherits: {inherits}")
    
    assert "Base" in inherits, "Base class not found in inherits"
    assert "other_func" in calls, "other_func not found in calls"
    assert "Sub" in line_map, "Sub class not found in line_map"
    
    print("\n✅ VERIFICATION: Phase 3 Skeletonizer works correctly.")

if __name__ == "__main__":
    try:
        test_f3_extraction()
    except Exception as e:
        print(f"❌ VERIFICATION FAILED: {e}")
        sys.exit(1)
