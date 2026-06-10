"""initial schema

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("date_of_start", sa.Date(), nullable=False),
        sa.Column("consider_for_networth", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_accounts_id"), "accounts", ["id"], unique=False)
    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_percentage", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_metrics_id"), "metrics", ["id"], unique=False)
    op.create_table(
        "account_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("date_of_entry", sa.Date(), nullable=False),
        sa.Column("current_value", sa.Numeric(15, 2), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "date_of_entry", name="uq_account_date"),
    )
    op.create_index(op.f("ix_account_entries_id"), "account_entries", ["id"], unique=False)
    op.create_table(
        "metric_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_entry_id", sa.Integer(), nullable=False),
        sa.Column("metric_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(15, 4), nullable=False),
        sa.ForeignKeyConstraint(["account_entry_id"], ["account_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_metric_entries_id"), "metric_entries", ["id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_metric_entries_id"), table_name="metric_entries")
    op.drop_table("metric_entries")
    op.drop_index(op.f("ix_account_entries_id"), table_name="account_entries")
    op.drop_table("account_entries")
    op.drop_index(op.f("ix_metrics_id"), table_name="metrics")
    op.drop_table("metrics")
    op.drop_index(op.f("ix_accounts_id"), table_name="accounts")
    op.drop_table("accounts")
