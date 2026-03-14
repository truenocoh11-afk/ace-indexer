import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.skeletonizer import Skeletonizer

def test_js_extraction():
    # The actual Skeletonizer class takes no arguments in __init__
    skeletonizer = Skeletonizer()
    
    js_code = """
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
class NormalClass { 
    method() {} 
}
"""
    
    # We need to simulate the skeletonize call
    # The method signature is skeletonize(code, filepath="")
    skeleton, line_map, calls, inherits = skeletonizer.skeletonize(js_code, filepath="test.js")
    
    print("--- SKELETON ---")
    print(skeleton)
    print("\n--- LINE MAP ---")
    for name, line in sorted(line_map.items(), key=lambda x: x[1]):
        print(f"  {name}: {line}")
        
    # Validation
    expected = [
        "getPb1", "getPb2", "getPb3", "getPb4", 
        "getPb5", "getPb6", "getPb7", "getPb8", 
        "normalFunction", "method", "NormalClass"
    ]
    
    missing = [e for e in expected if e not in line_map]
    if not missing:
        print("\n✅ Verification SUCCESS: All patterns captured!")
    else:
        print(f"\n❌ Verification FAILED: Missing symbols: {missing}")

if __name__ == "__main__":
    test_js_extraction()
