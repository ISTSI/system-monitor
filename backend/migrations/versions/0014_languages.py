"""Persist shared and personal UI language without changing existing preferences."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0014_languages"
down_revision = "0013_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_settings",
        sa.Column(
            "default_language",
            mysql.VARCHAR(16, charset="ascii", collation="ascii_bin"),
            nullable=False,
            server_default=sa.text("'en'"),
        ),
    )
    op.create_check_constraint(
        op.f("ck_application_settings_default_language"),
        "application_settings",
        "default_language IN ('en', 'pl')",
    )
    op.add_column(
        "user_preferences",
        sa.Column(
            "language",
            mysql.VARCHAR(16, charset="ascii", collation="ascii_bin"),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
    )
    op.create_check_constraint(
        op.f("ck_user_preferences_language"),
        "user_preferences",
        "language IN ('default', 'en', 'pl')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_user_preferences_language"), "user_preferences", type_="check")
    op.drop_column("user_preferences", "language")
    op.drop_constraint(
        op.f("ck_application_settings_default_language"), "application_settings", type_="check"
    )
    op.drop_column("application_settings", "default_language")
