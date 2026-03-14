import os
import sys

# Import the core logic
root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.append(root)
sys.path.append(os.path.join(root, "ace_engine"))

from ace_engine.core.skeletonizer import Skeletonizer
print(f"DEBUG: Skeletonizer imported from {Skeletonizer.__module__} at {getattr(sys.modules['ace_engine.core.skeletonizer'], '__file__', 'unknown')}")

def test_health_scan_logic():
    print("--- Testing Skeletonizer.scan_blind_spots ---")
    
    skeletonizer = Skeletonizer()
    
    # 1. Test Python Bare Except
    py_code = """
def bad():
    try:
        x = 1/0
    except:
        pass
"""
    results = skeletonizer.scan_blind_spots(py_code, "test.py")
    print("Python Results:", results)
    assert any(r['type'] in ('bare_except_pass', 'broad_except_pass', 'bare_except_doc') for r in results), f"Failed to detect bare except in Python. Results: {results}"

    # 2. Test JS Empty Catch
    js_code = """
function bad() {
    try {
        doSomething();
    } catch (e) {}
}
"""
    results = skeletonizer.scan_blind_spots(js_code, "test.js")
    print("JS Results:", results)
    assert any(r['type'] == 'empty_catch' or r['type'] == 'silent_catch' for r in results), "Failed to detect empty catch in JS"

    # 3. Test Clean File
    clean_code = "def good(): return 42"
    results = skeletonizer.scan_blind_spots(clean_code, "clean.py")
    assert len(results) == 0, "Clean file should have no diagnostics"

    print("PASS: Health scan logic verification successful.")

if __name__ == "__main__":
    try:
        test_health_scan_logic()
        print("\n[OK] Verification Gate 5 Passed (Core Logic)!")
    except Exception as e:
        print(f"\n[FAIL] Verification Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
