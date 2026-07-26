import os
import glob

THIRD_PARTY_MODULES = [
    'openpyxl',
    'pandas',
    'numpy',
    'reportlab',
    'PIL',
    'qrcode',
    'pyotp',
    'supabase',
    'zcatalyst_sdk',
    'psycopg2',
    'sqlalchemy',
    'alembic',
    'pydantic',
    'requests',
    'dotenv',
    'razorpay',
    'resend',
    'pywebpush',
    'apscheduler',
    'pytz',
    'google',
    'firebase_admin',
    'flask_mail',
    'flask_wtf',
    'flask_limiter',
    'flask_session',
    'flask_talisman',
    'tasks'
]

py_files = [f for f in glob.glob('**/*.py', recursive=True) if '.venv' not in f and 'scratch' not in f]

for path in py_files:
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    modified = False
    in_try_block = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Check if line is already inside a try block
        if stripped.startswith('try:'):
            in_try_block = True
        elif stripped.startswith('except') or stripped.startswith('finally'):
            in_try_block = False
            
        is_third_party = False
        if not in_try_block and (stripped.startswith('import ') or stripped.startswith('from ')):
            for mod in THIRD_PARTY_MODULES:
                if stripped.startswith(f'import {mod}') or stripped.startswith(f'from {mod}'):
                    is_third_party = True
                    break
        
        if is_third_party:
            indent = line[:len(line) - len(line.lstrip())]
            mod_name = stripped.split()[1].split('.')[0]
            new_lines.append(f"{indent}try:\n{indent}    {stripped}\n{indent}except Exception:\n{indent}    {mod_name} = None\n")
            modified = True
        else:
            new_lines.append(line)
            
    if modified:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"Safe-wrapped imports in: {path}")
