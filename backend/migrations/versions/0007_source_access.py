"""Explicit, expiring project/configuration-bound target and log-root approval."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import VARCHAR

revision = "0007_source_access"
down_revision = "0006_ssh_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ssh_credentials", sa.Column("expires_us", sa.BigInteger(), nullable=True))
    identity = VARCHAR(128, charset="ascii", collation="ascii_bin")
    digest = VARCHAR(64, charset="ascii", collation="ascii_bin")
    op.create_table(
        "source_access_approvals",
        sa.Column("project_id", identity, nullable=False),
        sa.Column("connection_id", identity, nullable=False),
        sa.Column(
            "connection_kind", VARCHAR(16, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("config_revision", sa.Integer(), nullable=False),
        sa.Column("route_digest", digest, nullable=False),
        sa.Column("roots_digest", digest, nullable=False),
        sa.Column("network_signature", digest, nullable=False),
        sa.Column("approved_by_user_id", identity, nullable=False),
        sa.Column("approved_us", sa.BigInteger(), nullable=False),
        sa.Column("expires_us", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "connection_id", name="pk_source_access_approvals"),
        sa.ForeignKeyConstraint(
            ["project_id", "connection_id", "connection_kind"],
            ["entity_identities.project_id", "entity_identities.id", "entity_identities.kind"],
            name="fk_source_access_scoped_connection",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "config_revision"],
            ["project_revisions.project_id", "project_revisions.revision"],
            name="fk_source_access_config_revision",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], name="fk_source_access_actor"
        ),
        sa.CheckConstraint(
            "connection_kind = 'connection'", name="ck_source_access_approvals_connection_kind"
        ),
        sa.CheckConstraint(
            "revision >= 1 AND config_revision >= 1", name="ck_source_access_approvals_revisions"
        ),
        sa.CheckConstraint("approved IN (0, 1)", name="ck_source_access_approvals_approved"),
        sa.CheckConstraint("expires_us > approved_us", name="ck_source_access_approvals_expiry"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
    )
    op.create_index(
        "ix_source_access_project_expiry", "source_access_approvals", ["project_id", "expires_us"]
    )


def downgrade() -> None:
    op.drop_table("source_access_approvals")
    op.drop_column("ssh_credentials", "expires_us")
