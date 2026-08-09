"""create tender.patrol_reports for people's patrol

Revision ID: 002_patrol_reports
Revises: 001_tenders
Create Date: 2026-08-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_patrol_reports"
down_revision: Union[str, None] = "001_tenders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patrol_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_name", sa.String(80), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("photo_bucket", sa.String(128), nullable=True),
        sa.Column("photo_key", sa.Text(), nullable=True),
        sa.Column("photo_content_type", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tender.tenders.id"],
            name="fk_patrol_reports_tender",
            ondelete="CASCADE",
        ),
        schema="tender",
    )
    op.create_index(
        "ix_patrol_reports_tender_id",
        "patrol_reports",
        ["tender_id"],
        schema="tender",
    )
    op.create_index(
        "ix_patrol_reports_created_at",
        "patrol_reports",
        ["created_at"],
        schema="tender",
    )


def downgrade() -> None:
    op.drop_index("ix_patrol_reports_created_at", table_name="patrol_reports", schema="tender")
    op.drop_index("ix_patrol_reports_tender_id", table_name="patrol_reports", schema="tender")
    op.drop_table("patrol_reports", schema="tender")
