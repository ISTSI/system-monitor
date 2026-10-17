"""Retain accounts/projects while adding Stage 01 preferences and labelled demo data."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0002_foundation_preferences"
down_revision: str | Sequence[str] | None = "0001_scoped_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.create_check_constraint(
        op.f("ck_users_must_change_password"), "users", "must_change_password IN (0, 1)"
    )
    op.create_table(
        "user_preferences",
        sa.Column(
            "user_id", mysql.VARCHAR(128, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "theme_mode", mysql.VARCHAR(16, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_preferences"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_preferences_user"),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_user_preferences_revision")),
        sa.CheckConstraint(
            "theme_mode IN ('default', 'light', 'dark', 'system')",
            name=op.f("ck_user_preferences_theme_mode"),
        ),
        **OPTIONS,
    )
    op.create_table(
        "application_settings",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "branding",
            mysql.VARCHAR(128, charset="utf8mb4", collation="utf8mb4_bin"),
            nullable=False,
        ),
        sa.Column(
            "default_theme_mode",
            mysql.VARCHAR(16, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_application_settings"),
        sa.CheckConstraint("id = 1", name=op.f("ck_application_settings_singleton")),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_application_settings_revision")),
        sa.CheckConstraint(
            "default_theme_mode IN ('light', 'dark', 'system')",
            name=op.f("ck_application_settings_default_theme_mode"),
        ),
        **OPTIONS,
    )
    op.create_table(
        "demo_snapshots",
        sa.Column(
            "project_id", mysql.VARCHAR(128, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", name="pk_demo_snapshots"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_demo_snapshots_project"),
        **OPTIONS,
    )


def downgrade() -> None:
    op.drop_table("demo_snapshots")
    op.drop_table("application_settings")
    op.drop_table("user_preferences")
    op.drop_constraint(op.f("ck_users_must_change_password"), "users", type_="check")
    op.drop_column("users", "must_change_password")
