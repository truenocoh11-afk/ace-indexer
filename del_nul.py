import os
def delete_nul():
    target_dir = os.path.abspath(".")
    target_path = "\\\\?\\" + target_dir + "\\nul"
    print("Trying to delete:", target_path)
    try:
        os.unlink(target_path)
        print("Success!")
    except Exception as e:
        print("Error:", e)
        
    for r, d, fl in os.walk(target_dir):
        if 'nul' in fl:
            p = "\\\\?\\" + r + "\\nul"
            print("Found in subfolder:", p)
            try: os.unlink(p)
            except Exception as e: print("Error:", e)

if __name__ == "__main__":
    delete_nul()
