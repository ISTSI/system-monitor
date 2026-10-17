"""MariaDB persistence for the scoped system/workspace foundation.

Projects are the application's Systems. Authentication remains global and does
not carry a mutable current project. Never serialize these ORM objects directly
to an API response: account/session/audit records contain protected fields.
"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def identifier() -> VARCHAR:
    """Preserve case-sensitive immutable fixture/import identities exactly."""
    return VARCHAR(128, charset="ascii", collation="ascii_bin")


def binary_text(length: int) -> VARCHAR:
    return VARCHAR(length, charset="utf8mb4", collation="utf8mb4_bin")


def verifier() -> VARCHAR:
    return VARCHAR(64, charset="ascii", collation="ascii_bin")


TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_bin",
}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_users"),
        UniqueConstraint("username_key", name="uq_users_username_key"),
        CheckConstraint("role IN ('administrator', 'inspector')", name="role"),
        CheckConstraint("enabled IN (0, 1)", name="enabled"),
        CheckConstraint("auth_version >= 1", name="auth_version"),
        CheckConstraint("must_change_password IN (0, 1)", name="must_change_password"),
        Index("ix_users_enabled_role", "enabled", "role"),
        TABLE_OPTIONS,
    )

    id: Mapped[str] = mapped_column(identifier())
    username_key: Mapped[str] = mapped_column(binary_text(256))
    display_name: Mapped[str] = mapped_column(binary_text(256))
    password_hash: Mapped[str] = mapped_column(binary_text(512))
    role: Mapped[str] = mapped_column(VARCHAR(16, charset="ascii", collation="ascii_bin"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    auth_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0")
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", name="pk_user_preferences"),
        ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_preferences_user"),
        CheckConstraint("revision >= 1", name="revision"),
        CheckConstraint("theme_mode IN ('default', 'light', 'dark', 'system')", name="theme_mode"),
        TABLE_OPTIONS,
    )

    user_id: Mapped[str] = mapped_column(identifier())
    revision: Mapped[int] = mapped_column(Integer)
    theme_mode: Mapped[str] = mapped_column(VARCHAR(16, charset="ascii", collation="ascii_bin"))


class ApplicationSetting(Base):
    __tablename__ = "application_settings"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_application_settings"),
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("revision >= 1", name="revision"),
        CheckConstraint(
            "default_theme_mode IN ('light', 'dark', 'system')", name="default_theme_mode"
        ),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=False)
    revision: Mapped[int] = mapped_column(Integer)
    branding: Mapped[str] = mapped_column(binary_text(128))
    default_theme_mode: Mapped[str] = mapped_column(
        VARCHAR(16, charset="ascii", collation="ascii_bin")
    )


class SecurityState(Base):
    """Singleton row locked for first-admin and last-admin invariants."""

    __tablename__ = "security_state"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_security_state"),
        CheckConstraint("id = 1", name="singleton"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        PrimaryKeyConstraint("token_hash", name="pk_auth_sessions"),
        ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_auth_sessions_user"),
        CheckConstraint("auth_version >= 1", name="auth_version"),
        CheckConstraint("expires_us > created_us", name="expiry"),
        Index("ix_auth_sessions_user_expiry", "user_id", "expires_us"),
        Index("ix_auth_sessions_expiry", "expires_us"),
        TABLE_OPTIONS,
    )

    token_hash: Mapped[str] = mapped_column(verifier())
    user_id: Mapped[str] = mapped_column(identifier())
    auth_version: Mapped[int] = mapped_column(Integer)
    csrf_hash: Mapped[str] = mapped_column(verifier())
    created_us: Mapped[int] = mapped_column(BigInteger)
    last_seen_us: Mapped[int] = mapped_column(BigInteger)
    expires_us: Mapped[int] = mapped_column(BigInteger)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_projects"),
        CheckConstraint("revision >= 1", name="revision"),
        CheckConstraint("archived IN (0, 1)", name="archived"),
        Index("ix_projects_archived_id", "archived", "id"),
        TABLE_OPTIONS,
    )

    id: Mapped[str] = mapped_column(identifier())
    name: Mapped[str] = mapped_column(binary_text(256))
    description: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))


class ProjectRevision(Base):
    """Retained snapshots keep a page's opening revision unambiguous."""

    __tablename__ = "project_revisions"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "revision", name="pk_project_revisions"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_project_revisions_project"),
        CheckConstraint("revision >= 1", name="revision"),
        TABLE_OPTIONS,
    )

    project_id: Mapped[str] = mapped_column(identifier())
    revision: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(binary_text(256))
    description: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))


class DemoSnapshot(Base):
    """Explicit read-only synthetic presentation, never an operational inventory."""

    __tablename__ = "demo_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", name="pk_demo_snapshots"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_demo_snapshots_project"),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    payload: Mapped[dict] = mapped_column(JSON)


class Workspace(Base):
    """A private server-issued page context, independent of its auth session."""

    __tablename__ = "workspaces"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", name="pk_workspaces"),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_workspaces_owner"),
        ForeignKeyConstraint(
            ["project_id", "opened_revision"],
            ["project_revisions.project_id", "project_revisions.revision"],
            name="fk_workspaces_project_revision",
        ),
        UniqueConstraint(
            "project_id", "id", "owner_user_id", name="uq_workspaces_project_id_owner"
        ),
        CheckConstraint("revision >= 1", name="revision"),
        CheckConstraint("opened_revision >= 1", name="opened_revision"),
        CheckConstraint("state IN ('active', 'detached', 'expired')", name="state"),
        Index("ix_workspaces_project_owner_state", "project_id", "owner_user_id", "state"),
        Index("ix_workspaces_state_expiry", "state", "expires_us"),
        TABLE_OPTIONS,
    )

    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    opened_revision: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    state: Mapped[str] = mapped_column(
        VARCHAR(16, charset="ascii", collation="ascii_bin"),
        default="active",
        server_default=text("'active'"),
    )
    created_us: Mapped[int] = mapped_column(BigInteger)
    expires_us: Mapped[int] = mapped_column(BigInteger)


class Audit(Base):
    """Only classification and identity fields; no arbitrary payload/text."""

    __tablename__ = "audit_events"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_audit_events"),
        ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_audit_events_actor"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_audit_events_project"),
        CheckConstraint(
            "actor_role IS NULL OR actor_role IN ('administrator', 'inspector')", name="actor_role"
        ),
        Index("ix_audit_events_project_created", "project_id", "created_us", "id"),
        Index("ix_audit_events_actor_created", "actor_user_id", "created_us", "id"),
        TABLE_OPTIONS,
    )

    id: Mapped[str] = mapped_column(identifier())
    actor_user_id: Mapped[str | None] = mapped_column(identifier(), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(
        VARCHAR(16, charset="ascii", collation="ascii_bin"), nullable=True
    )
    action: Mapped[str] = mapped_column(VARCHAR(64, charset="ascii", collation="ascii_bin"))
    project_id: Mapped[str | None] = mapped_column(identifier(), nullable=True)
    target_id: Mapped[str | None] = mapped_column(identifier(), nullable=True)
    created_us: Mapped[int] = mapped_column(BigInteger)
    outcome: Mapped[str] = mapped_column(VARCHAR(32, charset="ascii", collation="ascii_bin"))


AuditEvent = Audit
