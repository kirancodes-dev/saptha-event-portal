import os
import glob

py_files = [f for f in glob.glob('**/*.py', recursive=True) if '.venv' not in f and 'scratch' not in f]

for path in py_files:
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    modified = False
    for line in lines:
        if line.startswith('from google.cloud import firestore'):
            new_lines.append("try:\n    from google.cloud import firestore\nexcept ImportError:\n    firestore = None\n")
            modified = True
        elif line.startswith('from google.cloud.firestore_v1.base_query import FieldFilter'):
            new_lines.append("try:\n    from google.cloud.firestore_v1.base_query import FieldFilter\nexcept ImportError:\n    FieldFilter = None\n")
            modified = True
        elif line.startswith('from google import genai'):
            new_lines.append("try:\n    from google import genai\nexcept ImportError:\n    genai = None\n")
            modified = True
        elif line.startswith('import firebase_admin'):
            new_lines.append("try:\n    import firebase_admin\nexcept ImportError:\n    firebase_admin = None\n")
            modified = True
        elif line.startswith('from firebase_admin import'):
            new_lines.append("try:\n    " + line + "except ImportError:\n    credentials = firestore = auth = None\n")
            modified = True
        else:
            new_lines.append(line)
            
    if modified:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"Fixed imports in: {path}")
