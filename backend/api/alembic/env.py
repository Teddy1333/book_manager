import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add backend/api/ to sys.path so database package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db_manager import Base

target_metadata = Base.metadata

# Read DATABASE_URL; fall back to local SQLite
_DEFAULT_SQLITE = f"sqlite:///{Path(__file__).resolve().parent.parent / 'books.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_SQLITE)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL without connecting."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connect and apply."""
    config_section = context.config.get_section(context.config.config_ini_section, {})
    config_section["sqlalchemy.url"] = DATABASE_URL

    connectable = engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
