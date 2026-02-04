
import re
import os
import sys

# --- LOGIC TO TEST (v0.6.0 candidate) ---

def simulate(filepath, identifiers):
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return

    TEST_PATH_PATTERNS = [
        r'[/\\]tests?[/\\]', r'[/\\]specs?[/\\]', r'[/\\]__tests?__[/\\]',
        r'[/\\]mocks?[/\\]', r'[/\\]fixtures?[/\\]',
        r'\.test\.', r'\.spec\.', r'\.mock\.'
    ]
    
    DECL_PATTERNS = [
        # JS/TS
        r'(?:let|const|var)\s+{ident}\s*[=:;]',
        r'export\s+(?:let|const|var)\s+{ident}',
        r'export\s+(?:default\s+)?(?:function|class)\s+{ident}',
        r'(?:public|private|protected)?\s*{ident}\s*[=:]',
        # Python
        r'^{ident}\s*=\s*',
        r'^{ident}\s*:\s*\w+\s*=',
        r'self\.{ident}\s*=',
        r'def\s+{ident}\s*\(',
        r'class\s+{ident}\s*[\(:]',
        r'async\s+def\s+{ident}\s*\(',
        # General
        r'function\s+{ident}\s*\(',
        r'{ident}\s*=\s*function\s*\(',
        r'{ident}\s*=\s*\([^)]*\)\s*=>',
    ]

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return

    # Check mitigations
    is_test = any(re.search(p, filepath, re.IGNORECASE) for p in TEST_PATH_PATTERNS)
    base_boost = 0.3 if is_test else 1.0
    
    total_boost = 0
    
    print(f"\n📂 File: {os.path.basename(filepath)}")
    if is_test: print("   ⚠️  [TEST DETECTED] Boost penalty active")
    
    for ident in identifiers:
        found = False
        for pattern_template in DECL_PATTERNS:
            pattern = pattern_template.format(ident=re.escape(ident))
            if re.search(pattern, content, re.MULTILINE):
                print(f"   ✅ MATCH: '{ident}' -> Pattern: {pattern}")
                total_boost += base_boost
                found = True
                break # One per identifier
        
        if not found:
            print(f"   ❌ NO MATCH: '{ident}'")
            
    # Cap logic
    final_boost = min(total_boost, 1.5)
    print(f"   🚀 Final Boost: +{final_boost}")
    return final_boost

# --- TEST CASES ---

# 1. lastAgentStats
print("--- TEST CASE 1: lastAgentStats ---")
simulate(r"c:\Users\Julian\Desktop\OVERLAY V2\monitor\server.js", ["lastAgentStats"])
simulate(r"c:\Users\Julian\Desktop\OVERLAY V2\refactor-v3\src\ui\overlay\main.ts", ["lastAgentStats"])

# 2. tleCache
print("\n--- TEST CASE 2: tleCache ---")
simulate(r"c:\Users\Julian\Desktop\OVERLAY V2\monitor\server.js", ["tleCache"])
simulate(r"c:\Users\Julian\Desktop\OVERLAY V2\refactor-v3\public\vdo\lib.js", ["tleCache"])

# 3. Class definition
print("\n--- TEST CASE 3: StarlinkMonitor (Class) ---")
simulate(r"c:\Users\Julian\Desktop\OVERLAY V2\refactor-v3\public\agent\network_monitor.py", ["StarlinkMonitor"])

print("\n-------------------------------------------")
