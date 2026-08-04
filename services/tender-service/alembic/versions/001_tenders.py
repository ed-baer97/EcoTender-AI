"""create tender.tenders with PostGIS point

Revision ID: 001_tenders
Revises:
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "001_tenders"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS tender")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "tenders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="KZ"),
        sa.Column("source_code", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("customer_external_id", sa.String(64), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("region_code", sa.String(32), nullable=True),
        sa.Column("region_name", sa.String(128), nullable=True),
        sa.Column("eco_category", sa.String(64), nullable=True),
        sa.Column("procurement_method", sa.String(64), nullable=True),
        sa.Column("participants_count", sa.Integer(), nullable=True),
        sa.Column("area_sq_m", sa.Float(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("winner_name", sa.Text(), nullable=True),
        sa.Column("amendments_count", sa.Integer(), nullable=True),
        sa.Column("amendment_amount_ratio", sa.Float(), nullable=True),
        sa.Column("market_amount_est", sa.Float(), nullable=True),
        sa.Column("contractor_wins_2y", sa.Integer(), nullable=True),
        sa.Column("contractor_win_rate", sa.Float(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("risk_band", sa.String(16), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("geom", Geography(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extras", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("source_code", "external_id", name="uq_tender_source_ext"),
        schema="tender",
    )
    op.create_index("ix_tender_country", "tenders", ["country_code"], schema="tender")
    op.create_index("ix_tender_source", "tenders", ["source_code"], schema="tender")
    op.create_index("ix_tender_eco", "tenders", ["eco_category"], schema="tender")
    op.create_index("ix_tender_risk", "tenders", ["risk_score"], schema="tender")
    op.create_index("ix_tender_band", "tenders", ["risk_band"], schema="tender")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tender_geom ON tender.tenders USING GIST (geom)"
    )


def downgrade() -> None:
    op.drop_table("tenders", schema="tender")
