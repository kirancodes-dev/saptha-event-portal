import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, '.')
import os
from models import DATABASE_TYPE, db

print(f"DATABASE_TYPE from env: {os.environ.get('DATABASE_TYPE')}")
print(f"DATABASE_TYPE evaluated: {DATABASE_TYPE}")
print(f"db instance class: {db.__class__.__name__}")
