"""Allow documented servers without a remote connection; preserve scoped references."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0016_optional_connection"
down_revision = "0015_remember_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "servers",
        "connection_id",
        existing_type=mysql.VARCHAR(128, charset="ascii", collation="ascii_bin"),
        existing_nullable=False,
        nullable=True,
    )


def downgrade() -> None:
    # Never delete documented servers or invent a connection to fit the old model.
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM servers WHERE connection_id IS NULL")):
        raise RuntimeError(
            "Assign connections to all servers before downgrading the optional-connection schema."
        )
    op.alter_column(
        "servers",
        "connection_id",
        existing_type=mysql.VARCHAR(128, charset="ascii", collation="ascii_bin"),
        existing_nullable=True,
        nullable=False,
    )
