"""Establish the migration chain without creating domain tables.

Revision ID: 0001_migration_baseline
Revises:
Create Date: 2026-08-02
"""

revision: str = "0001_migration_baseline"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
