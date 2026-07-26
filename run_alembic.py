import os
try:
    from dotenv import load_dotenv
except Exception:
    dotenv = None
try:
    from alembic.config import Config
except Exception:
    alembic = None
try:
    from alembic import command
except Exception:
    alembic = None

def run():
    # Load environment variables from .env
    load_dotenv()

    # Create an Alembic config object
    alembic_cfg = Config("alembic.ini")

    # Ensure the database URL is set in the config from the environment
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Execute the revision command
    print("Generating initial schema migration...")
    command.revision(alembic_cfg, message="initial_schema", autogenerate=True)
    print("Migration generated successfully.")

if __name__ == "__main__":
    run()
