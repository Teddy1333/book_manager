# Requirements Document

## Introduction

Add Alembic database migration support to the FastAPI backend API service. This replaces the current `Base.metadata.create_all()` auto-creation approach with versioned, repeatable migrations managed by Alembic. Three faked migration files simulate schema evolution to the current database state (core tables → reading progress → notes and share links). Migrations are executed manually via Docker Compose rather than automatically on container startup.

## Glossary

- **API_Service**: The FastAPI backend application located at `backend/api/`
- **Alembic**: A database migration tool for SQLAlchemy that tracks schema changes via versioned migration scripts
- **Migration_Script**: A Python file in the Alembic versions directory that defines `upgrade()` and `downgrade()` functions for a schema change
- **DATABASE_URL**: Environment variable containing the database connection string (PostgreSQL in Docker, SQLite fallback for local development)
- **Migration_Chain**: An ordered sequence of migration scripts linked via `down_revision` references forming a linear history
- **Schema_State**: The complete set of tables, columns, indexes, and constraints in the database at a given point

## Requirements

### Requirement 1: Alembic Dependency

**User Story:** As a developer, I want Alembic added as a project dependency, so that migration tooling is available in the runtime environment.

#### Acceptance Criteria

1. THE API_Service SHALL include `alembic` as a pinned dependency in `backend/api/requirements.txt`
2. WHEN the Docker image is built, THE API_Service SHALL have the `alembic` package installed and importable

### Requirement 2: Alembic Configuration

**User Story:** As a developer, I want a properly configured Alembic setup, so that migration commands work against the correct database.

#### Acceptance Criteria

1. THE API_Service SHALL contain an `alembic.ini` file at `backend/api/alembic.ini` that defines the Alembic configuration
2. THE API_Service SHALL contain an `alembic/` directory at `backend/api/alembic/` with an `env.py` file and a `versions/` subdirectory
3. WHEN Alembic reads its configuration, THE API_Service SHALL provide `env.py` that reads the `DATABASE_URL` environment variable for the database connection string
4. IF the `DATABASE_URL` environment variable is not set, THEN THE API_Service SHALL fall back to a local SQLite connection string in `env.py`
5. THE API_Service SHALL configure `env.py` to import and use the `Base.metadata` target from `database.db_manager` for autogenerate support
6. THE API_Service SHALL configure `alembic.ini` to point `script_location` to the `alembic/` directory

### Requirement 3: Migration Scripts for Core Tables

**User Story:** As a developer, I want a first migration script that creates the core tables, so that the foundational schema is captured as a versioned migration.

#### Acceptance Criteria

1. THE Migration_Chain SHALL include a first migration script with `down_revision = None` that creates the `users` table with columns: `id` (Integer, primary key, indexed), `username` (String, unique, indexed), `hashed_password` (String)
2. THE Migration_Chain SHALL include in the first migration script the creation of the `books` table with columns: `id` (Integer, primary key, indexed), `title` (String, indexed), `author` (String), `isbn` (String, nullable), `publisher` (String, nullable), `pages` (String, nullable), `description` (Text, nullable), `cover_url` (String, nullable), `source` (String, server_default "manual"), `owner_id` (Integer, ForeignKey to `users.id`)
3. THE Migration_Chain SHALL include in the first migration script the creation of the `tags` table with columns: `id` (Integer, primary key, indexed), `name` (String, unique, indexed, not null)
4. THE Migration_Chain SHALL include in the first migration script the creation of the `book_tags` junction table with columns: `book_id` (Integer, ForeignKey to `books.id`, primary key), `tag_id` (Integer, ForeignKey to `tags.id`, primary key)

### Requirement 4: Migration Script for Reading Progress

**User Story:** As a developer, I want a second migration script that adds reading progress tracking, so that the schema evolution is captured incrementally.

#### Acceptance Criteria

1. THE Migration_Chain SHALL include a second migration script whose `down_revision` references the first migration's revision identifier
2. THE Migration_Chain SHALL include in the second migration script the creation of the `reading_progress` table with columns: `id` (Integer, primary key, indexed), `book_id` (Integer, ForeignKey to `books.id`, not null), `current_page` (Integer, not null), `total_pages` (Integer, nullable), `source` (String, server_default "manual"), `created_at` (DateTime, not null)

### Requirement 5: Migration Script for Notes and Share Links

**User Story:** As a developer, I want a third migration script that adds notes and share link tables, so that the full current schema is reached through migrations.

#### Acceptance Criteria

1. THE Migration_Chain SHALL include a third migration script whose `down_revision` references the second migration's revision identifier
2. THE Migration_Chain SHALL include in the third migration script the creation of the `notes` table with columns: `id` (Integer, primary key, indexed), `book_id` (Integer, ForeignKey to `books.id`, not null), `owner_id` (Integer, ForeignKey to `users.id`, not null), `text` (Text, not null), `page` (Integer, nullable), `note_type` (String, server_default "manual"), `image_path` (String, nullable), `audio_path` (String, nullable), `created_at` (DateTime, not null)
3. THE Migration_Chain SHALL include in the third migration script the creation of the `share_links` table with columns: `id` (Integer, primary key, indexed), `book_id` (Integer, ForeignKey to `books.id`, not null), `token` (String, unique, indexed, not null), `created_at` (DateTime, not null)

### Requirement 6: Schema Fidelity

**User Story:** As a developer, I want the final migration state to match the current SQLAlchemy models exactly, so that there is no drift between migrations and code.

#### Acceptance Criteria

1. WHEN all three migration scripts are applied in sequence, THE Schema_State SHALL match the table definitions in `backend/api/database/db_models.py` exactly in terms of column types, constraints, indexes, and foreign keys
2. WHEN `alembic upgrade head` is executed against an empty database, THE Migration_Chain SHALL produce the complete current schema without errors
3. WHEN `alembic downgrade base` is executed, THE Migration_Chain SHALL drop all tables created by the migrations without errors

### Requirement 7: Removal of Auto-Creation

**User Story:** As a developer, I want the automatic table creation removed from application startup, so that schema management is handled exclusively through Alembic migrations.

#### Acceptance Criteria

1. THE API_Service SHALL NOT execute `Base.metadata.create_all(bind=engine)` in `backend/api/main.py`
2. WHEN the API_Service starts, THE API_Service SHALL assume the database schema already exists from prior migration execution

### Requirement 8: Manual Migration Execution

**User Story:** As a developer, I want migrations to run only via explicit manual command, so that I have full control over when schema changes are applied.

#### Acceptance Criteria

1. THE API_Service SHALL NOT execute migrations automatically on container startup
2. WHEN a developer runs `docker compose exec api alembic upgrade head`, THE Migration_Chain SHALL apply all pending migrations to the database
3. THE API_Service Dockerfile SHALL remain unchanged (no entrypoint script for auto-migration)
