"""Add the current schema to the older customer-portal database without deleting data."""

import argparse
import json
from pathlib import Path

from alembic.autogenerate import produce_migrations
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations, ops
from alembic.script import ScriptDirectory
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, inspect, text

from app.db.base import Base
from app.db.engine import get_engine
from app.domain import models  # noqa: F401

LEGACY_REVISION = "0009_customer_agent_actions"
LEGACY_VECTOR_COLUMNS = {"embedding_1536_legacy", "embedding_profile", "embedding_1024_profile"}
ADDITIVE_OPERATIONS = (ops.CreateTableOp, ops.AddColumnOp, ops.CreateIndexOp,
                       ops.CreateUniqueConstraintOp, ops.CreateForeignKeyOp)


def schema_operations(connection):
    context = MigrationContext.configure(connection, opts={
        "include_object": lambda obj, name, kind, reflected, compare_to:
            kind != "table" or name in Base.metadata.tables,
    })
    migration = produce_migrations(context, Base.metadata)
    result = []

    def visit(operation):
        if isinstance(operation, ops.OpContainer):
            for child in operation.ops:
                visit(child)
        elif isinstance(operation, ADDITIVE_OPERATIONS):
            result.append(operation)
        elif isinstance(operation, ops.DropColumnOp) and operation.table_name == "knowledge_chunks" and operation.column_name in LEGACY_VECTOR_COLUMNS:
            pass
        elif isinstance(operation, ops.DropIndexOp):
            # Existing indexes are retained, including indexes on archived vectors.
            pass
        else:
            raise RuntimeError(f"Unsupported schema change: {operation.to_diff_tuple()!r}")

    visit(migration.upgrade_ops)
    return context, result


def preserve_vectors(connection):
    columns = {column["name"]: column["type"] for column in inspect(connection).get_columns("knowledge_chunks")}
    expected = Base.metadata.tables["knowledge_chunks"].c.embedding.type.dim
    if isinstance(columns["embedding"], Vector) and columns["embedding"].dim == expected:
        return False
    if (expected != 1024 or not isinstance(columns["embedding"], Vector)
            or columns["embedding"].dim != 1536 or "embedding_1536_legacy" in columns
            or not isinstance(columns.get("embedding_1024"), Vector)
            or columns["embedding_1024"].dim != expected):
        raise RuntimeError("The embedding layout is not the supported 1536/1024 legacy layout.")
    connection.execute(text("ALTER TABLE knowledge_chunks RENAME COLUMN embedding TO embedding_1536_legacy"))
    connection.execute(text("ALTER TABLE knowledge_chunks RENAME COLUMN embedding_1024 TO embedding"))
    return True


def verify_booking_constraint(connection):
    constraint = connection.execute(text("""
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public' AND t.relname = 'appointment_slots' AND c.contype = 'x'
    """)).scalar()
    if not constraint or "technician_id" not in constraint or "tstzrange" not in constraint:
        raise RuntimeError("The technician appointment exclusion constraint is missing.")


def upgrade(connection):
    revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if revision != [LEGACY_REVISION]:
        raise RuntimeError(f"Expected legacy revision {LEGACY_REVISION}; found {revision!r}.")
    archived = preserve_vectors(connection)
    context, changes = schema_operations(connection)
    operations = Operations(context)
    for operation in changes:
        if isinstance(operation, ops.AddColumnOp):
            # Autogeneration emits constraints separately; avoid adding them twice.
            column = operation.column
            operations.add_column(operation.table_name, Column(column.name, column.type,
                nullable=column.nullable,
                server_default=column.server_default.arg if column.server_default else None),
                schema=operation.schema)
        else:
            operations.invoke(operation)
    _, remaining = schema_operations(connection)
    if remaining:
        raise RuntimeError("Schema reconciliation left unapplied changes.")
    verify_booking_constraint(connection)
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    connection.execute(text("UPDATE alembic_version SET version_num = :head WHERE version_num = :legacy"),
                       {"head": head, "legacy": LEGACY_REVISION})
    return {"revision": head, "additive_operations": len(changes), "archived_1536_vectors": archived}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the upgrade after taking a database backup.")
    args = parser.parse_args()
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            result = upgrade(connection)
            if args.apply:
                transaction.commit()
            else:
                transaction.rollback()
        except Exception:
            transaction.rollback()
            raise
    print(json.dumps({**result, "applied": args.apply}))


if __name__ == "__main__":
    main()
