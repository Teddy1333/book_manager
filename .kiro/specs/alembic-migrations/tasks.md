# Implementation Plan: Alembic Database Migrations

## Overview

Add Alembic migration infrastructure to `backend/api/`, replacing `Base.metadata.create_all()` with three versioned migration scripts that incrementally build the schema. All implementation is Python targeting the existing FastAPI backend.

## Tasks

- [x] 1. Add Alembic dependencies and configuration
  - [x] 1.1 Add alembic and Mako to requirements.txt
    - Append `alembic==1.15.2` and `Mako==1.3.9` to `backend/api/requirements.txt`
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Create alembic.ini configuration file
    - Create `backend/api/alembic.ini` with `script_location = alembic`, placeholder `sqlalchemy.url`, and standard logging config
    - _Requirements: 2.1, 2.6_

  - [x] 1.3 Create alembic/env.py
    - Create `backend/api/alembic/env.py` that reads `DATABASE_URL` from environment, falls back to SQLite, imports `Base.metadata` from `database.db_manager`, and implements both offline and online migration runners
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [x] 1.4 Create alembic/script.py.mako template
    - Create `backend/api/alembic/script.py.mako` with standard Mako template for generating new migration files
    - _Requirements: 2.2_

- [x] 2. Checkpoint - Verify Alembic infrastructure
  - Ensure alembic directory structure is correct and env.py imports succeed, ask the user if questions arise.

- [x] 3. Create migration scripts
  - [x] 3.1 Create 001_core_tables.py migration
    - Create `backend/api/alembic/versions/001_core_tables.py` with `revision="0001"`, `down_revision=None`
    - Implement `upgrade()`: create `users` table (id, username, hashed_password) with indexes, `books` table (id, title, author, isbn, publisher, pages, description, cover_url, source, owner_id) with indexes and FK, `tags` table (id, name) with indexes, `book_tags` junction table (book_id, tag_id) with FKs and composite PK
    - Implement `downgrade()`: drop tables in reverse dependency order
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.2 Create 002_reading_progress.py migration
    - Create `backend/api/alembic/versions/002_reading_progress.py` with `revision="0002"`, `down_revision="0001"`
    - Implement `upgrade()`: create `reading_progress` table (id, book_id, current_page, total_pages, source, created_at) with index and FK
    - Implement `downgrade()`: drop index and table
    - _Requirements: 4.1, 4.2_

  - [x] 3.3 Create 003_notes_share_links.py migration
    - Create `backend/api/alembic/versions/003_notes_share_links.py` with `revision="0003"`, `down_revision="0002"`
    - Implement `upgrade()`: create `notes` table (id, book_id, owner_id, text, page, note_type, image_path, audio_path, created_at) with index and FKs, create `share_links` table (id, book_id, token, created_at) with indexes and FK
    - Implement `downgrade()`: drop indexes and tables in reverse order
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 4. Remove auto-creation from main.py
  - [x] 4.1 Remove Base.metadata.create_all from main.py
    - Remove `db_models.Base.metadata.create_all(bind=engine)` from `backend/api/main.py`
    - Remove the `engine` import from `database.db_manager` if no longer used
    - Keep `db_models` import for relationship registration
    - _Requirements: 7.1, 7.2, 8.1_

- [x] 5. Checkpoint - Verify migration chain
  - Ensure all migration files exist with correct revision chain (None → 0001 → 0002 → 0003), ask the user if questions arise.

- [x] 6. Write property-based tests for migrations
  - [x] 6.1 Write property test for upgrade/downgrade round-trip
    - **Property 1: Migration upgrade/downgrade round-trip**
    - Create test in `backend/api/tests/test_migrations.py` that applies `alembic upgrade head` then `alembic downgrade base` on a fresh SQLite database and asserts no application tables remain
    - **Validates: Requirements 6.3**

  - [x] 6.2 Write property test for schema equivalence
    - **Property 2: Migration-model schema equivalence**
    - Create test that compares schema from `alembic upgrade head` against `Base.metadata.create_all()` output, verifying table names, column names, column types, nullability, primary keys, foreign keys, unique constraints, and indexes match
    - **Validates: Requirements 6.1**

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Migrations are executed manually via `docker compose exec api alembic upgrade head`
- The `alembic_version` table is managed automatically by Alembic

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["3.1"] },
    { "id": 2, "tasks": ["3.2", "4.1"] },
    { "id": 3, "tasks": ["3.3"] },
    { "id": 4, "tasks": ["6.1", "6.2"] }
  ]
}
```
