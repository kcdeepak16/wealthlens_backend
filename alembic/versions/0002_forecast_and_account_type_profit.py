"""forecast and account type profit

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account_type_profit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_type", sa.String(), nullable=False),
        sa.Column("date_of_entry", sa.Date(), nullable=False),
        sa.Column("profit_percentage", sa.Numeric(8, 4), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_type", "date_of_entry", name="uq_type_date"),
    )
    op.create_index(op.f("ix_account_type_profit_id"), "account_type_profit", ["id"], unique=False)
    op.create_table(
        "forecast_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_forecast_settings_id"), "forecast_settings", ["id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_forecast_settings_id"), table_name="forecast_settings")
    op.drop_table("forecast_settings")
    op.drop_index(op.f("ix_account_type_profit_id"), table_name="account_type_profit")
    op.drop_table("account_type_profit")
