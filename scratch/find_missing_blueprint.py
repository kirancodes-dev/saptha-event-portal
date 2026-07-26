import glob

py_files = [f for f in glob.glob('**/*.py', recursive=True) if '.venv' not in f and 'scratch' not in f]

for path in py_files:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'Blueprint(' in content or 'Blueprint' in content:
        if 'from flask import' not in content and 'import flask' not in content and 'Blueprint = ' not in content:
            print(f"MISSING BLUEPRINT IMPORT IN: {path}")
