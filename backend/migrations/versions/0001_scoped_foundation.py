"""Global accounts and project-scoped workspace foundation.

Revision ID: 0001_scoped_foundation
Revises: none (fresh schema; no legacy runtime database was present)

MariaDB DDL is not transactional. Back up before an authorized real migration;
this revision deliberately does not infer scope or rewrite existing user data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001_scoped_foundation"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> mysql.VARCHAR:
    return mysql.VARCHAR(128, charset="ascii", collation="ascii_bin")


def _text(length: int) -> mysql.VARCHAR:
    return mysql.VARCHAR(length, charset="utf8mb4", collation="utf8mb4_bin")


def _ascii(length: int) -> mysql.VARCHAR:
    return mysql.VARCHAR(length, charset="ascii", collation="ascii_bin")


_TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_bin",
}


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", _id(), nullable=False),
        sa.Column("username_key", _text(256), nullable=False),
        sa.Column("display_name", _text(256), nullable=False),
        sa.Column("password_hash", _text(512), nullable=False),
        sa.Column("role", _ascii(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("auth_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username_key", name="uq_users_username_key"),
        sa.CheckConstraint("role IN ('administrator', 'inspector')", name=op.f("ck_users_role")),
        sa.CheckConstraint("enabled IN (0, 1)", name=op.f("ck_users_enabled")),
        sa.CheckConstraint("auth_version >= 1", name=op.f("ck_users_auth_version")),
        **_TABLE_OPTIONS,
    )
    op.create_index("ix_users_enabled_role", "users", ["enabled", "role"])
    op.create_table(
        "security_state",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=False),
        sa.PrimaryKeyConstraint("id", name="pk_security_state"),
        sa.CheckConstraint("id = 1", name=op.f("ck_security_state_singleton")),
        **_TABLE_OPTIONS,
    )
    # Always present before bootstrap; concurrent first-admin attempts lock it.
    op.bulk_insert(sa.table("security_state", sa.column("id", sa.Integer())), [{"id": 1}])
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", _ascii(64), nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("csrf_hash", _ascii(64), nullable=False),
        sa.Column("created_us", sa.BigInteger(), nullable=False),
        sa.Column("last_seen_us", sa.BigInteger(), nullable=False),
        sa.Column("expires_us", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name="pk_auth_sessions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_auth_sessions_user"),
        sa.CheckConstraint("auth_version >= 1", name=op.f("ck_auth_sessions_auth_version")),
        sa.CheckConstraint("expires_us > created_us", name=op.f("ck_auth_sessions_expiry")),
        **_TABLE_OPTIONS,
    )
    op.create_index("ix_auth_sessions_user_expiry", "auth_sessions", ["user_id", "expires_us"])
    op.create_index("ix_auth_sessions_expiry", "auth_sessions", ["expires_us"])
    op.create_table(
        "projects",
        sa.Column("id", _id(), nullable=False),
        sa.Column("name", _text(256), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_projects_revision")),
        sa.CheckConstraint("archived IN (0, 1)", name=op.f("ck_projects_archived")),
        **_TABLE_OPTIONS,
    )
    op.create_index("ix_projects_archived_id", "projects", ["archived", "id"])
    op.create_table(
        "project_revisions",
        sa.Column("project_id", _id(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("name", _text(256), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "revision", name="pk_project_revisions"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_project_revisions_project"
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_project_revisions_revision")),
        **_TABLE_OPTIONS,
    )
    op.create_table(
        "workspaces",
        sa.Column("project_id", _id(), nullable=False),
        sa.Column("id", _id(), nullable=False),
        sa.Column("owner_user_id", _id(), nullable=False),
        sa.Column("opened_revision", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("state", _ascii(16), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_us", sa.BigInteger(), nullable=False),
        sa.Column("expires_us", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "id", name="pk_workspaces"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_workspaces_owner"),
        sa.ForeignKeyConstraint(
            ["project_id", "opened_revision"],
            ["project_revisions.project_id", "project_revisions.revision"],
            name="fk_workspaces_project_revision",
        ),
        sa.UniqueConstraint(
            "project_id", "id", "owner_user_id", name="uq_workspaces_project_id_owner"
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_workspaces_revision")),
        sa.CheckConstraint("opened_revision >= 1", name=op.f("ck_workspaces_opened_revision")),
        sa.CheckConstraint(
            "state IN ('active', 'detached', 'expired')", name=op.f("ck_workspaces_state")
        ),
        **_TABLE_OPTIONS,
    )
    op.create_index(
        "ix_workspaces_project_owner_state", "workspaces", ["project_id", "owner_user_id", "state"]
    )
    op.create_index("ix_workspaces_state_expiry", "workspaces", ["state", "expires_us"])
    op.create_table(
        "audit_events",
        sa.Column("id", _id(), nullable=False),
        sa.Column("actor_user_id", _id(), nullable=True),
        sa.Column("actor_role", _ascii(16), nullable=True),
        sa.Column("action", _ascii(64), nullable=False),
        sa.Column("project_id", _id(), nullable=True),
        sa.Column("target_id", _id(), nullable=True),
        sa.Column("created_us", sa.BigInteger(), nullable=False),
        sa.Column("outcome", _ascii(32), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_audit_events_actor"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_audit_events_project"),
        sa.CheckConstraint(
            "actor_role IS NULL OR actor_role IN ('administrator', 'inspector')",
            name=op.f("ck_audit_events_actor_role"),
        ),
        **_TABLE_OPTIONS,
    )
    op.create_index(
        "ix_audit_events_project_created", "audit_events", ["project_id", "created_us", "id"]
    )
    op.create_index(
        "ix_audit_events_actor_created", "audit_events", ["actor_user_id", "created_us", "id"]
    )


def downgrade() -> None:
    # This explicit operator migration removes the foundation data. The serving
    # application never invokes it; restore a matching backup for real rollback.
    op.drop_table("audit_events")
    op.drop_table("workspaces")
    op.drop_table("project_revisions")
    op.drop_table("projects")
    op.drop_table("auth_sessions")
    op.drop_table("security_state")
    op.drop_table("users")
