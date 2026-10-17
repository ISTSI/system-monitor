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
from sqlalchemy.dialects.mysql import LONGTEXT, VARCHAR
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
    """Preserved Stage 01 synthetic fixture and Stage 02 migration marker."""

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


class TopologyState(Base):
    """Current canonical config and bounded semantic undo/redo revision stacks."""

    __tablename__ = "topology_states"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", name="pk_topology_states"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_topology_states_project"),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    config: Mapped[dict] = mapped_column(JSON)
    undo_stack: Mapped[list] = mapped_column(JSON)
    redo_stack: Mapped[list] = mapped_column(JSON)


class TopologySnapshot(Base):
    """Immutable complete snapshots retain historic names and source definitions."""

    __tablename__ = "topology_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "revision", name="pk_topology_snapshots"),
        ForeignKeyConstraint(
            ["project_id", "revision"],
            ["project_revisions.project_id", "project_revisions.revision"],
            name="fk_topology_snapshots_revision",
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    revision: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSON)


class EntityIdentity(Base):
    """Tombstones prohibit reusing an immutable ID for a new entity/type."""

    __tablename__ = "entity_identities"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", name="pk_entity_identities"),
        UniqueConstraint("project_id", "id", "kind", name="uq_entity_identities_kind"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_entity_identities_project"),
        CheckConstraint("deleted IN (0, 1)", name="deleted"),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    kind: Mapped[str] = mapped_column(VARCHAR(16, charset="ascii", collation="ascii_bin"))
    name: Mapped[str] = mapped_column(binary_text(256))
    deleted: Mapped[bool] = mapped_column(Boolean)


class NamedTopology:
    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    name: Mapped[str] = mapped_column(binary_text(256))
    name_key: Mapped[str] = mapped_column(verifier())
    payload: Mapped[dict] = mapped_column(JSON)


class EntityNameSnapshot(Base):
    """Compact name/deletion history survives full-config undo retention."""

    __tablename__ = "topology_entity_names"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", "revision", name="pk_topology_entity_names"),
        ForeignKeyConstraint(
            ["project_id", "id"],
            ["entity_identities.project_id", "entity_identities.id"],
            name="fk_topology_entity_names_identity",
        ),
        ForeignKeyConstraint(
            ["project_id", "revision"],
            ["project_revisions.project_id", "project_revisions.revision"],
            name="fk_topology_entity_names_revision",
        ),
        CheckConstraint("deleted IN (0, 1)", name="deleted"),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    revision: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(binary_text(256))
    deleted: Mapped[bool] = mapped_column(Boolean)


def topology_constraints(table: str, *extra: object) -> tuple:
    return (
        PrimaryKeyConstraint("project_id", "id", name=f"pk_{table}"),
        ForeignKeyConstraint(
            ["project_id", "id"],
            ["entity_identities.project_id", "entity_identities.id"],
            name=f"fk_{table}_identity",
        ),
        UniqueConstraint("project_id", "name_key", name=f"uq_{table}_project_name"),
        *extra,
        TABLE_OPTIONS,
    )


class Subsystem(NamedTopology, Base):
    __tablename__ = "subsystems"
    __table_args__ = topology_constraints("subsystems")


class ConnectionProfile(NamedTopology, Base):
    __tablename__ = "connection_profiles"
    __table_args__ = topology_constraints(
        "connection_profiles",
        ForeignKeyConstraint(
            ["project_id", "jump_connection_id"],
            ["connection_profiles.project_id", "connection_profiles.id"],
            name="fk_connections_scoped_jump",
        ),
    )
    jump_connection_id: Mapped[str | None] = mapped_column(identifier(), nullable=True)


class ParserProfile(NamedTopology, Base):
    __tablename__ = "parser_profiles"
    __table_args__ = topology_constraints("parser_profiles")


class Server(NamedTopology, Base):
    __tablename__ = "servers"
    __table_args__ = topology_constraints(
        "servers",
        ForeignKeyConstraint(
            ["project_id", "subsystem_id"],
            ["subsystems.project_id", "subsystems.id"],
            name="fk_servers_scoped_subsystem",
        ),
        ForeignKeyConstraint(
            ["project_id", "connection_id"],
            ["connection_profiles.project_id", "connection_profiles.id"],
            name="fk_servers_scoped_connection",
        ),
    )
    subsystem_id: Mapped[str] = mapped_column(identifier())
    connection_id: Mapped[str] = mapped_column(identifier())


class Process(NamedTopology, Base):
    __tablename__ = "processes"
    __table_args__ = topology_constraints(
        "processes",
        ForeignKeyConstraint(
            ["project_id", "server_id"],
            ["servers.project_id", "servers.id"],
            name="fk_processes_scoped_server",
        ),
        ForeignKeyConstraint(
            ["project_id", "parser_id"],
            ["parser_profiles.project_id", "parser_profiles.id"],
            name="fk_processes_scoped_parser",
        ),
    )
    server_id: Mapped[str] = mapped_column(identifier())
    parser_id: Mapped[str] = mapped_column(identifier())


class Flow(NamedTopology, Base):
    __tablename__ = "flows"
    __table_args__ = topology_constraints(
        "flows",
        ForeignKeyConstraint(
            ["project_id", "source_process_id"],
            ["processes.project_id", "processes.id"],
            name="fk_flows_scoped_source",
        ),
        ForeignKeyConstraint(
            ["project_id", "target_process_id"],
            ["processes.project_id", "processes.id"],
            name="fk_flows_scoped_target",
        ),
    )
    source_process_id: Mapped[str] = mapped_column(identifier())
    target_process_id: Mapped[str] = mapped_column(identifier())


class SharedView(NamedTopology, Base):
    __tablename__ = "shared_views"
    __table_args__ = topology_constraints("shared_views")


class ViewNode(Base):
    __tablename__ = "view_nodes"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "view_id", "element_id", name="pk_view_nodes"),
        ForeignKeyConstraint(
            ["project_id", "view_id"],
            ["shared_views.project_id", "shared_views.id"],
            name="fk_view_nodes_scoped_view",
        ),
        ForeignKeyConstraint(
            ["project_id", "element_id"],
            ["entity_identities.project_id", "entity_identities.id"],
            name="fk_view_nodes_scoped_element",
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    view_id: Mapped[str] = mapped_column(identifier())
    element_id: Mapped[str] = mapped_column(identifier())
    geometry: Mapped[dict] = mapped_column(JSON)


class ViewFlow(Base):
    __tablename__ = "view_flows"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "view_id", "flow_id", name="pk_view_flows"),
        ForeignKeyConstraint(
            ["project_id", "view_id"],
            ["shared_views.project_id", "shared_views.id"],
            name="fk_view_flows_scoped_view",
        ),
        ForeignKeyConstraint(
            ["project_id", "flow_id"],
            ["flows.project_id", "flows.id"],
            name="fk_view_flows_scoped_flow",
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    view_id: Mapped[str] = mapped_column(identifier())
    flow_id: Mapped[str] = mapped_column(identifier())


class ConfigPreview(Base):
    __tablename__ = "config_previews"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", name="pk_config_previews"),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_config_previews_owner"),
        ForeignKeyConstraint(
            ["project_id", "expected_revision"],
            ["project_revisions.project_id", "project_revisions.revision"],
            name="fk_config_previews_revision",
        ),
        Index(
            "ix_config_previews_project_owner_expiry", "project_id", "owner_user_id", "expires_us"
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    auth_version: Mapped[int] = mapped_column(Integer)
    expected_revision: Mapped[int] = mapped_column(Integer)
    source_project_id: Mapped[str] = mapped_column(identifier())
    digest: Mapped[str] = mapped_column(verifier())
    config: Mapped[dict] = mapped_column(JSON)
    expires_us: Mapped[int] = mapped_column(BigInteger)


class HistoryJob(Base):
    """Private capture and its offline investigation; never serialize the config."""

    __tablename__ = "history_jobs"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", name="pk_history_jobs"),
        ForeignKeyConstraint(
            ["project_id", "workspace_id", "owner_user_id"],
            ["workspaces.project_id", "workspaces.id", "workspaces.owner_user_id"],
            name="fk_history_jobs_scoped_workspace_owner",
        ),
        ForeignKeyConstraint(
            ["project_id", "config_revision"],
            ["project_revisions.project_id", "project_revisions.revision"],
            name="fk_history_jobs_scoped_revision",
        ),
        UniqueConstraint("project_id", "id", "owner_user_id", name="uq_history_jobs_owner"),
        CheckConstraint("snapshot_revision >= 0 AND event_count >= 0", name="counts"),
        Index("ix_history_jobs_owner_state", "owner_user_id", "status"),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    workspace_id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    auth_version: Mapped[int] = mapped_column(Integer)
    auth_session_hash: Mapped[str] = mapped_column(verifier())
    config_revision: Mapped[int] = mapped_column(Integer)
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    process_ids: Mapped[list] = mapped_column(JSON)
    from_us: Mapped[int] = mapped_column(BigInteger)
    to_us: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(binary_text(32))
    snapshot_revision: Mapped[int] = mapped_column(BigInteger)
    event_count: Mapped[int] = mapped_column(BigInteger)
    parse_issue_count: Mapped[int] = mapped_column(BigInteger)
    downloaded_bytes: Mapped[int] = mapped_column(BigInteger)
    expanded_bytes: Mapped[int] = mapped_column(BigInteger)
    created_us: Mapped[int] = mapped_column(BigInteger)
    errors: Mapped[list] = mapped_column(JSON)


class HistorySource(Base):
    __tablename__ = "history_sources"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "job_id", "id", name="pk_history_sources"),
        ForeignKeyConstraint(
            ["project_id", "job_id"],
            ["history_jobs.project_id", "history_jobs.id"],
            name="fk_history_sources_scoped_job",
        ),
        ForeignKeyConstraint(
            ["project_id", "process_id", "process_kind"],
            ["entity_identities.project_id", "entity_identities.id", "entity_identities.kind"],
            name="fk_history_sources_scoped_process",
        ),
        CheckConstraint("process_kind = 'process'", name="process_kind"),
        UniqueConstraint(
            "project_id", "job_id", "id", "process_id", name="uq_history_sources_process"
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    job_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    process_id: Mapped[str] = mapped_column(identifier())
    process_kind: Mapped[str] = mapped_column(
        VARCHAR(16, charset="ascii", collation="ascii_bin"),
        default="process",
        server_default=text("'process'"),
    )
    remote_path: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(binary_text(16))
    cache_name: Mapped[str] = mapped_column(identifier())
    checksum: Mapped[str | None] = mapped_column(verifier(), nullable=True)
    status: Mapped[str] = mapped_column(binary_text(32))
    error_code: Mapped[str | None] = mapped_column(binary_text(64), nullable=True)
    event_count: Mapped[int] = mapped_column(BigInteger)
    downloaded_bytes: Mapped[int] = mapped_column(BigInteger)
    expanded_bytes: Mapped[int] = mapped_column(BigInteger)
    manifest: Mapped[dict] = mapped_column(JSON)


class HistoryEvent(Base):
    __tablename__ = "history_events"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "job_id", "event_id", name="pk_history_events"),
        ForeignKeyConstraint(
            ["project_id", "job_id", "source_revision_id", "process_id"],
            [
                "history_sources.project_id",
                "history_sources.job_id",
                "history_sources.id",
                "history_sources.process_id",
            ],
            name="fk_history_events_scoped_source",
        ),
        UniqueConstraint("project_id", "job_id", "capture_seq", name="uq_history_events_seq"),
        Index(
            "ix_history_events_order",
            "project_id",
            "job_id",
            "timestamp_us",
            "process_id",
            "source_revision_id",
            "member_order",
            "byte_start",
            "event_id",
        ),
        Index(
            "ix_history_events_source_order",
            "project_id",
            "job_id",
            "source_revision_id",
            "member_order",
            "byte_start",
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    job_id: Mapped[str] = mapped_column(identifier())
    event_id: Mapped[str] = mapped_column(identifier())
    process_id: Mapped[str] = mapped_column(identifier())
    source_revision_id: Mapped[str] = mapped_column(identifier())
    capture_seq: Mapped[int] = mapped_column(BigInteger)
    timestamp_us: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    member_order: Mapped[int] = mapped_column(Integer)
    byte_start: Mapped[int] = mapped_column(BigInteger)
    raw_line: Mapped[str] = mapped_column(LONGTEXT)
    payload: Mapped[dict] = mapped_column(JSON)


class HistoryCursor(Base):
    __tablename__ = "history_cursors"
    __table_args__ = (
        PrimaryKeyConstraint("token_hash", name="pk_history_cursors"),
        ForeignKeyConstraint(
            ["project_id", "job_id", "owner_user_id"],
            ["history_jobs.project_id", "history_jobs.id", "history_jobs.owner_user_id"],
            name="fk_history_cursors_scoped_owner_job",
        ),
        Index("ix_history_cursors_expiry", "expires_us"),
        TABLE_OPTIONS,
    )
    token_hash: Mapped[str] = mapped_column(verifier())
    project_id: Mapped[str] = mapped_column(identifier())
    job_id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    auth_version: Mapped[int] = mapped_column(Integer)
    query_hash: Mapped[str] = mapped_column(verifier())
    snapshot_revision: Mapped[int] = mapped_column(BigInteger)
    max_seq: Mapped[int] = mapped_column(BigInteger)
    after_key: Mapped[list] = mapped_column(JSON)
    expires_us: Mapped[int] = mapped_column(BigInteger)


class HistoryDownload(Base):
    __tablename__ = "history_downloads"
    __table_args__ = (
        PrimaryKeyConstraint("token_hash", name="pk_history_downloads"),
        ForeignKeyConstraint(
            ["project_id", "job_id", "source_revision_id"],
            ["history_sources.project_id", "history_sources.job_id", "history_sources.id"],
            name="fk_history_downloads_scoped_source",
        ),
        ForeignKeyConstraint(
            ["project_id", "job_id", "owner_user_id"],
            ["history_jobs.project_id", "history_jobs.id", "history_jobs.owner_user_id"],
            name="fk_history_downloads_scoped_owner_job",
        ),
        Index("ix_history_downloads_expiry", "expires_us"),
        TABLE_OPTIONS,
    )
    token_hash: Mapped[str] = mapped_column(verifier())
    project_id: Mapped[str] = mapped_column(identifier())
    job_id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    source_revision_id: Mapped[str] = mapped_column(identifier())
    auth_version: Mapped[int] = mapped_column(Integer)
    expires_us: Mapped[int] = mapped_column(BigInteger)
