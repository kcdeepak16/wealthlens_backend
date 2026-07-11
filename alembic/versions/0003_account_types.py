"""account types

Revision ID: 0003
Revises: 027dbe8bdaa6
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "027dbe8bdaa6"
branch_labels = None
depends_on = None


DEFAULT_ACCOUNT_TYPES = [
    ("bank_account", "Bank Account"),
    ("mutual_fund", "Mutual Fund"),
    ("stocks", "Stocks"),
    ("pf", "PF"),
    ("lent", "Lent"),
    ("liquid_funds", "Liquid Funds"),
    ("other", "Other"),
]


def _label_for_type(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def upgrade():
    op.create_table(
        "account_types",
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("value"),
    )
    op.create_index(op.f("ix_account_types_value"), "account_types", ["value"], unique=False)

    connection = op.get_bind()
    account_types = dict(DEFAULT_ACCOUNT_TYPES)
    existing = connection.execute(sa.text("SELECT DISTINCT type FROM accounts")).fetchall()
    for row in existing:
        account_type = row[0]
        account_types.setdefault(account_type, _label_for_type(account_type))

    for value, label in account_types.items():
        connection.execute(
            sa.text("INSERT INTO account_types (value, label) VALUES (:value, :label)"),
            {"value": value, "label": label},
        )


def downgrade():
    op.drop_index(op.f("ix_account_types_value"), table_name="account_types")
    op.drop_table("account_types")
