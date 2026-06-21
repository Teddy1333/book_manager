"""Property-based tests for Alembic migrations.

These tests verify correctness properties of the migration scripts
against the SQLAlchemy model definitions.
"""

import os
import sys
import tempfile

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, MetaData

# We need Base.metadata populated with all models.
# db_models uses datetime.UTC which requires Python 3.11+.
# Patch it for Python 3.10 compatibility if needed.
import datetime
if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc

from database.db_manager import Base
import database.db_models  # noqa: F401 — registers models on Base.metadata


BACKEND_API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALEMBIC_INI_PATH = os.path.join(BACKEND_API_DIR, "alembic.ini")

# Expected application tables from the models
EXPECTED_APP_TABLES = {
    "users", "books", "tags", "book_tags",
    "reading_progress", "notes", "share_links",
}


def _make_alembic_config(db_url: str) -> Config:
    """Create an Alembic Config pointing at a specific database URL."""
    cfg = Config(ALEMBIC_INI_PATH)
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", os.path.join(BACKEND_API_DIR, "alembic"))
    return cfg


def _normalize_type(type_obj) -> str:
    """Normalize a SQLAlchemy column type to a comparable string.

    SQLite reflects types in generic form, so we normalize to uppercase
    class name for comparison.
    """
    return type(type_obj).__name__.upper()


class TestMigrationRoundTrip:
    """Property 1: Migration upgrade/downgrade round-trip.

    For any empty database, applying `alembic upgrade head` followed by
    `alembic downgrade base` SHALL result in a database with no application
    tables remaining (only the `alembic_version` table may persist, empty).

    **Validates: Requirements 6.3**
    """

    def setup_method(self):
        """Create a temporary SQLite database for testing."""
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_url = f"sqlite:///{self._tmp.name}"

    def teardown_method(self):
        """Clean up temporary database."""
        os.unlink(self._tmp.name)
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

    def test_upgrade_downgrade_leaves_no_app_tables(self):
        """After upgrade head then downgrade base, no application tables remain."""
        cfg = _make_alembic_config(self.db_url)
        os.environ["DATABASE_URL"] = self.db_url

        # Apply all migrations
        command.upgrade(cfg, "head")

        # Revert all migrations
        command.downgrade(cfg, "base")

        # Inspect remaining tables
        engine = create_engine(self.db_url)
        inspector = inspect(engine)
        remaining_tables = set(inspector.get_table_names())
        engine.dispose()

        # Only alembic_version may remain
        app_tables_remaining = remaining_tables - {"alembic_version"}
        assert app_tables_remaining == set(), (
            f"Application tables remain after downgrade: {app_tables_remaining}"
        )

    def test_upgrade_creates_expected_tables(self):
        """After upgrade head, all expected application tables exist."""
        cfg = _make_alembic_config(self.db_url)
        os.environ["DATABASE_URL"] = self.db_url

        # Apply all migrations
        command.upgrade(cfg, "head")

        # Inspect tables
        engine = create_engine(self.db_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        engine.dispose()

        # All expected tables should be present
        tables.discard("alembic_version")
        assert tables == EXPECTED_APP_TABLES, (
            f"Table mismatch after upgrade.\n"
            f"  Missing: {EXPECTED_APP_TABLES - tables}\n"
            f"  Extra: {tables - EXPECTED_APP_TABLES}"
        )


class TestSchemaEquivalence:
    """Property 2: Migration-model schema equivalence.

    For any empty database, the schema produced by `alembic upgrade head`
    SHALL be identical to the schema produced by `Base.metadata.create_all()`
    in terms of table names, column names, column types, nullability constraints,
    primary keys, foreign keys, unique constraints, and indexes.

    **Validates: Requirements 6.1**
    """

    def setup_method(self):
        """Create two temporary SQLite databases for comparison."""
        # Database 1: schema from Alembic migrations
        self._tmp_migration = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp_migration.close()
        self.migration_db_url = f"sqlite:///{self._tmp_migration.name}"

        # Database 2: schema from Base.metadata.create_all()
        self._tmp_models = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp_models.close()
        self.models_db_url = f"sqlite:///{self._tmp_models.name}"

        # Apply Alembic migrations to db1
        cfg = _make_alembic_config(self.migration_db_url)
        os.environ["DATABASE_URL"] = self.migration_db_url
        command.upgrade(cfg, "head")

        # Apply Base.metadata.create_all() to db2
        engine = create_engine(self.models_db_url)
        Base.metadata.create_all(bind=engine)
        engine.dispose()

        # Create inspectors
        self.migration_engine = create_engine(self.migration_db_url)
        self.models_engine = create_engine(self.models_db_url)
        self.migration_inspector = inspect(self.migration_engine)
        self.models_inspector = inspect(self.models_engine)

    def teardown_method(self):
        """Clean up temporary databases."""
        self.migration_engine.dispose()
        self.models_engine.dispose()
        os.unlink(self._tmp_migration.name)
        os.unlink(self._tmp_models.name)
        # Restore environment
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

    def test_table_names_match(self):
        """Tables produced by migrations match tables from models."""
        migration_tables = set(self.migration_inspector.get_table_names())
        models_tables = set(self.models_inspector.get_table_names())

        # Alembic adds alembic_version table; exclude it from comparison
        migration_tables.discard("alembic_version")

        assert migration_tables == models_tables, (
            f"Table mismatch.\n"
            f"  Only in migrations: {migration_tables - models_tables}\n"
            f"  Only in models: {models_tables - migration_tables}"
        )

    def test_column_names_match(self):
        """Column names for each table match between migration and model schemas."""
        models_tables = set(self.models_inspector.get_table_names())

        for table in models_tables:
            migration_cols = {
                c["name"] for c in self.migration_inspector.get_columns(table)
            }
            models_cols = {
                c["name"] for c in self.models_inspector.get_columns(table)
            }
            assert migration_cols == models_cols, (
                f"Column mismatch in table '{table}'.\n"
                f"  Only in migrations: {migration_cols - models_cols}\n"
                f"  Only in models: {models_cols - migration_cols}"
            )

    def test_column_types_match(self):
        """Column types for each table match between migration and model schemas."""
        models_tables = set(self.models_inspector.get_table_names())

        for table in models_tables:
            migration_cols = {
                c["name"]: _normalize_type(c["type"])
                for c in self.migration_inspector.get_columns(table)
            }
            models_cols = {
                c["name"]: _normalize_type(c["type"])
                for c in self.models_inspector.get_columns(table)
            }
            for col_name in models_cols:
                assert col_name in migration_cols, (
                    f"Column '{col_name}' missing in migration schema for table '{table}'"
                )
                assert migration_cols[col_name] == models_cols[col_name], (
                    f"Type mismatch for '{table}.{col_name}': "
                    f"migration={migration_cols[col_name]}, model={models_cols[col_name]}"
                )

    def test_column_nullability_matches(self):
        """Column nullability for each table matches between schemas."""
        models_tables = set(self.models_inspector.get_table_names())

        for table in models_tables:
            migration_cols = {
                c["name"]: c["nullable"]
                for c in self.migration_inspector.get_columns(table)
            }
            models_cols = {
                c["name"]: c["nullable"]
                for c in self.models_inspector.get_columns(table)
            }
            for col_name in models_cols:
                assert col_name in migration_cols, (
                    f"Column '{col_name}' missing in migration schema for table '{table}'"
                )
                assert migration_cols[col_name] == models_cols[col_name], (
                    f"Nullability mismatch for '{table}.{col_name}': "
                    f"migration={migration_cols[col_name]}, model={models_cols[col_name]}"
                )

    def test_primary_keys_match(self):
        """Primary key constraints match between schemas."""
        models_tables = set(self.models_inspector.get_table_names())

        for table in models_tables:
            migration_pk = self.migration_inspector.get_pk_constraint(table)
            models_pk = self.models_inspector.get_pk_constraint(table)
            assert set(migration_pk["constrained_columns"]) == set(
                models_pk["constrained_columns"]
            ), (
                f"PK mismatch in table '{table}': "
                f"migration={migration_pk['constrained_columns']}, "
                f"model={models_pk['constrained_columns']}"
            )

    def test_foreign_keys_match(self):
        """Foreign key constraints match between schemas."""
        models_tables = set(self.models_inspector.get_table_names())

        for table in models_tables:
            migration_fks = self.migration_inspector.get_foreign_keys(table)
            models_fks = self.models_inspector.get_foreign_keys(table)

            # Normalize FKs to comparable tuples: (constrained_columns, referred_table, referred_columns)
            def _normalize_fks(fks):
                return {
                    (
                        tuple(sorted(fk["constrained_columns"])),
                        fk["referred_table"],
                        tuple(sorted(fk["referred_columns"])),
                    )
                    for fk in fks
                }

            migration_fk_set = _normalize_fks(migration_fks)
            models_fk_set = _normalize_fks(models_fks)

            assert migration_fk_set == models_fk_set, (
                f"FK mismatch in table '{table}'.\n"
                f"  Only in migrations: {migration_fk_set - models_fk_set}\n"
                f"  Only in models: {models_fk_set - migration_fk_set}"
            )

    def test_unique_constraints_match(self):
        """Unique constraints match between schemas."""
        models_tables = set(self.models_inspector.get_table_names())

        for table in models_tables:
            migration_uq = self.migration_inspector.get_unique_constraints(table)
            models_uq = self.models_inspector.get_unique_constraints(table)

            # Normalize to sets of frozensets of column names
            migration_uq_set = {
                frozenset(uq["column_names"]) for uq in migration_uq
            }
            models_uq_set = {
                frozenset(uq["column_names"]) for uq in models_uq
            }

            assert migration_uq_set == models_uq_set, (
                f"Unique constraint mismatch in table '{table}'.\n"
                f"  Only in migrations: {migration_uq_set - models_uq_set}\n"
                f"  Only in models: {models_uq_set - migration_uq_set}"
            )

    def test_indexes_match(self):
        """Indexes match between schemas."""
        models_tables = set(self.models_inspector.get_table_names())

        for table in models_tables:
            migration_indexes = self.migration_inspector.get_indexes(table)
            models_indexes = self.models_inspector.get_indexes(table)

            # Normalize indexes to comparable tuples: (column_names, unique)
            def _normalize_indexes(indexes):
                return {
                    (tuple(sorted(idx["column_names"])), idx["unique"])
                    for idx in indexes
                }

            migration_idx_set = _normalize_indexes(migration_indexes)
            models_idx_set = _normalize_indexes(models_indexes)

            assert migration_idx_set == models_idx_set, (
                f"Index mismatch in table '{table}'.\n"
                f"  Only in migrations: {migration_idx_set - models_idx_set}\n"
                f"  Only in models: {models_idx_set - migration_idx_set}"
            )
