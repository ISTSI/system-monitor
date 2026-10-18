"""Persist each login's explicit 30-day remember choice; retain existing policy."""

import sqlalchemy as sa
from alembic import op

revision = "0015_remember_login"
down_revision = "0014_languages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("remember_me", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.create_check_constraint(
        op.f("ck_auth_sessions_remember_me"), "auth_sessions", "remember_me IN (0, 1)"
    )


def downgrade() -> None:
    # Older serving code cannot distinguish the opt-in from ordinary sessions.
    # End remembered sessions before removing that policy marker.
    op.execute(sa.text("DELETE FROM auth_sessions WHERE remember_me = 1"))
    op.drop_constraint(op.f("ck_auth_sessions_remember_me"), "auth_sessions", type_="check")
    op.drop_column("auth_sessions", "remember_me")
