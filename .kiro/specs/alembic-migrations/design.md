# Design Document

## Overview

This design adds Alembic database migration support to the FastAPI backend (`backend/api/`). It replaces the runtime `Base.metadata.create_all()` call with three versioned migration scripts that build the schema incrementally: core tables → reading progress → notes and share links. Migrations are triggered manually via `docker compose exec api alembic upgrade head`.

## Architecture

### Component Diagram

```
backend/api/
├── alembic.ini                  # Alembic configuration (script_location, sqlalchemy.url placeholder)
├── alembic/
│   ├── env.py                   # Runtime config: reads DATABASE_URL, imports Base.metadata
│   ├── script.py.mako           # Template for new migrations
│   └── versions/
│       ├── 001_core_tables.py          # users, books, tags, book_tags
│       ├── 002_reading_progress.py     # reading_progress
│       └── 003_notes_share_links.py    # notes, share_links
├── database/
│   ├── db_manager.py            # Engine, SessionLocal, Base (unchanged)
│   └── db_models.py             # Declarative models (unchanged)
├── main.py                      # FastAPI app (create_all removed)
└── requirements.txt             # alembic dependency added
```

### Data Flow

1. Developer runs `docker compose exec api alembic upgrade head`
2. Alembic reads `alembic.ini` → finds `script_location = alembic`
3. `env.py` executes → reads `DATABASE_URL` from environment (falls back to SQLite)
4. `env.py` imports `Base.metadata` from `database.db_manager` for target metadata
5. Alembic determines current revision from `alembic_version` table in database
6. Alembic applies pending migration scripts in chain order

## Components and Interfaces

### 1. alembic.ini

Standard Alembic configuration file at `backend/api/alembic.ini`.

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = sqlite:///books.db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

The `sqlalchemy.url` value in the ini file is a placeholder — `env.py` overrides it at runtime with the `DATABASE_URL` environment variable.

### 2. alembic/env.py

Configures Alembic runtime to use the project's database connection and model metadata.

```python
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
```

### 3. Migration Script 1: Core Tables

File: `alembic/versions/001_core_tables.py`

```python
"""Create core tables: users, books, tags, book_tags

Revision ID: 0001
Revises: None
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("hashed_password", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"])
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("isbn", sa.String(), nullable=True),
        sa.Column("publisher", sa.String(), nullable=True),
        sa.Column("pages", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.String(), nullable=True),
        sa.Column("source", sa.String(), server_default="manual", nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_books_id"), "books", ["id"])
    op.create_index(op.f("ix_books_title"), "books", ["title"])

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tags_id"), "tags", ["id"])
    op.create_index(op.f("ix_tags_name"), "tags", ["name"], unique=True)

    op.create_table(
        "book_tags",
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"]),
        sa.PrimaryKeyConstraint("book_id", "tag_id"),
    )


def downgrade() -> None:
    op.drop_table("book_tags")
    op.drop_index(op.f("ix_tags_name"), table_name="tags")
    op.drop_index(op.f("ix_tags_id"), table_name="tags")
    op.drop_table("tags")
    op.drop_index(op.f("ix_books_title"), table_name="books")
    op.drop_index(op.f("ix_books_id"), table_name="books")
    op.drop_table("books")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
```

### 4. Migration Script 2: Reading Progress

File: `alembic/versions/002_reading_progress.py`

```python
"""Create reading_progress table

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reading_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("current_page", sa.Integer(), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(), server_default="manual", nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reading_progress_id"), "reading_progress", ["id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_reading_progress_id"), table_name="reading_progress")
    op.drop_table("reading_progress")
```

### 5. Migration Script 3: Notes and Share Links

File: `alembic/versions/003_notes_share_links.py`

```python
"""Create notes and share_links tables

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("note_type", sa.String(), server_default="manual", nullable=True),
        sa.Column("image_path", sa.String(), nullable=True),
        sa.Column("audio_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notes_id"), "notes", ["id"])

    op.create_table(
        "share_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_share_links_id"), "share_links", ["id"])
    op.create_index(op.f("ix_share_links_token"), "share_links", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_share_links_token"), table_name="share_links")
    op.drop_index(op.f("ix_share_links_id"), table_name="share_links")
    op.drop_table("share_links")
    op.drop_index(op.f("ix_notes_id"), table_name="notes")
    op.drop_table("notes")
```

### 6. main.py Modification

Remove the `create_all` line:

```python
# REMOVE this line:
# db_models.Base.metadata.create_all(bind=engine)
```

The import of `db_models` can stay (routers may depend on the module being imported for relationship registration), but `engine` is no longer imported into `main.py` unless needed elsewhere.

### 7. requirements.txt Addition

Add Alembic with a pinned version:

```
alembic==1.15.2
Mako==1.3.9
```

Mako is Alembic's template dependency — pinning it avoids transitive version drift.

### CLI Interface

| Command | Effect |
|---------|--------|
| `docker compose exec api alembic upgrade head` | Apply all pending migrations |
| `docker compose exec api alembic downgrade base` | Revert all migrations |
| `docker compose exec api alembic current` | Show current revision |
| `docker compose exec api alembic history` | Show migration history |
| `docker compose exec api alembic upgrade +1` | Apply next single migration |
| `docker compose exec api alembic downgrade -1` | Revert last migration |

### env.py Internal Interface

| Symbol | Type | Source |
|--------|------|--------|
| `DATABASE_URL` | `str` | `os.getenv("DATABASE_URL", sqlite_fallback)` |
| `target_metadata` | `MetaData` | `database.db_manager.Base.metadata` |

## Data Models

No new data models are introduced. The migration scripts reproduce the existing models defined in `db_models.py`:

- `users` — application users with credentials
- `books` — book entries owned by users
- `tags` — categorical labels for books
- `book_tags` — many-to-many junction between books and tags
- `reading_progress` — page-tracking entries for books
- `notes` — text/media notes attached to books
- `share_links` — unique token-based public links to books

Alembic adds one tracking table automatically:
- `alembic_version` — single-row table storing the current migration revision string

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `DATABASE_URL` not set | `env.py` falls back to `sqlite:///books.db` in the working directory |
| Database unreachable during migration | Alembic raises `OperationalError`; migration aborts with no partial changes (transactional DDL on PostgreSQL) |
| Migration already applied | Alembic reports "Already at head" and exits cleanly |
| Downgrade drops tables with data | Data is lost; this is expected behavior for downgrade operations |
| API starts without migrations applied | Queries fail with `ProgrammingError` (relation does not exist); this is intentional — migrations must be run first |

## Testing Strategy

### Integration Tests

The primary validation mechanism for this feature is integration testing against a real database:

1. **Full upgrade path**: Run `alembic upgrade head` on an empty SQLite database; verify all tables exist with correct schemas
2. **Full downgrade path**: After upgrade, run `alembic downgrade base`; verify all application tables are removed
3. **Schema equivalence**: Compare the schema from migrations against `Base.metadata.create_all()` output
4. **Individual migration verification**: Apply each migration step and verify the expected tables exist

### Smoke Tests

- `alembic` is importable in the container environment
- `alembic.ini` exists and has correct `script_location`
- `env.py` imports `Base.metadata` from `database.db_manager`
- `main.py` does not contain `create_all`
- Migration chain is unbroken (`down_revision` values link correctly)

### Property-Based Tests

Two properties are testable (see Correctness Properties below):
- Round-trip: upgrade then downgrade leaves database clean
- Equivalence: migration schema matches model metadata

Both operate against a test SQLite database to keep execution fast.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Migration upgrade/downgrade round-trip

*For any* empty database, applying `alembic upgrade head` followed by `alembic downgrade base` SHALL result in a database with no application tables remaining (only the `alembic_version` table may persist, empty).

**Validates: Requirements 6.3**

### Property 2: Migration-model schema equivalence

*For any* empty database, the schema produced by `alembic upgrade head` SHALL be identical to the schema produced by `Base.metadata.create_all()` in terms of table names, column names, column types, nullability constraints, primary keys, foreign keys, unique constraints, and indexes.

**Validates: Requirements 6.1**
