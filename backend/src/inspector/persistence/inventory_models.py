"""Project-scoped inventory provenance; raw uploads live only in restricted staging."""

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from inspector.persistence.models import TABLE_OPTIONS, Base, binary_text, identifier, verifier


class InventorySource(Base):
    __tablename__ = "inventory_sources"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", name="pk_inventory_sources"),
        UniqueConstraint("project_id", "name_key", name="uq_inventory_sources_name"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_inventory_sources_project"),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    name: Mapped[str] = mapped_column(binary_text(256))
    name_key: Mapped[str] = mapped_column(verifier())
    created_us: Mapped[int] = mapped_column(BigInteger)


class InventoryUpload(Base):
    __tablename__ = "inventory_uploads"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", name="pk_inventory_uploads"),
        UniqueConstraint(
            "project_id",
            "id",
            "source_id",
            "owner_user_id",
            name="uq_inventory_uploads_owner_source",
        ),
        ForeignKeyConstraint(
            ["project_id", "source_id"],
            ["inventory_sources.project_id", "inventory_sources.id"],
            name="fk_inventory_uploads_source",
        ),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_inventory_uploads_owner"),
        Index("ix_inventory_uploads_expiry", "expires_us"),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    source_id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    auth_version: Mapped[int] = mapped_column(Integer)
    expected_revision: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(binary_text(256))
    digest: Mapped[str] = mapped_column(verifier())
    manifest_digest: Mapped[str] = mapped_column(verifier())
    summary: Mapped[dict] = mapped_column(JSON)
    expires_us: Mapped[int] = mapped_column(BigInteger)


class InventoryPreview(Base):
    __tablename__ = "inventory_previews"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", name="pk_inventory_previews"),
        ForeignKeyConstraint(
            ["project_id", "upload_id", "source_id", "owner_user_id"],
            [
                "inventory_uploads.project_id",
                "inventory_uploads.id",
                "inventory_uploads.source_id",
                "inventory_uploads.owner_user_id",
            ],
            name="fk_inventory_previews_upload_owner_source",
        ),
        ForeignKeyConstraint(
            ["project_id", "source_id"],
            ["inventory_sources.project_id", "inventory_sources.id"],
            name="fk_inventory_previews_source",
        ),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_inventory_previews_owner"),
        Index("ix_inventory_previews_expiry", "expires_us"),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    source_id: Mapped[str] = mapped_column(identifier())
    upload_id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    auth_version: Mapped[int] = mapped_column(Integer)
    expected_revision: Mapped[int] = mapped_column(Integer)
    content_digest: Mapped[str] = mapped_column(verifier())
    manifest_digest: Mapped[str] = mapped_column(verifier())
    mapping_digest: Mapped[str] = mapped_column(verifier())
    digest: Mapped[str] = mapped_column(verifier())
    document: Mapped[dict] = mapped_column(JSON)
    expires_us: Mapped[int] = mapped_column(BigInteger)


class InventoryHostMapping(Base):
    __tablename__ = "inventory_host_mappings"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "source_id", "alias", name="pk_inventory_host_mappings"),
        ForeignKeyConstraint(
            ["project_id", "source_id"],
            ["inventory_sources.project_id", "inventory_sources.id"],
            name="fk_inventory_host_mappings_source",
        ),
        ForeignKeyConstraint(
            ["project_id", "server_id"],
            ["entity_identities.project_id", "entity_identities.id"],
            name="fk_inventory_host_mappings_server",
        ),
        ForeignKeyConstraint(
            ["project_id", "connection_id"],
            ["entity_identities.project_id", "entity_identities.id"],
            name="fk_inventory_host_mappings_connection",
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    source_id: Mapped[str] = mapped_column(identifier())
    alias: Mapped[str] = mapped_column(identifier())
    server_id: Mapped[str] = mapped_column(identifier())
    connection_id: Mapped[str] = mapped_column(identifier())
    baseline: Mapped[dict] = mapped_column(JSON)


class InventoryProcessMapping(Base):
    __tablename__ = "inventory_process_mappings"
    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id", "source_id", "alias", "local_id", name="pk_inventory_process_mappings"
        ),
        ForeignKeyConstraint(
            ["project_id", "source_id", "alias"],
            [
                "inventory_host_mappings.project_id",
                "inventory_host_mappings.source_id",
                "inventory_host_mappings.alias",
            ],
            name="fk_inventory_process_mappings_host",
        ),
        ForeignKeyConstraint(
            ["project_id", "process_id"],
            ["entity_identities.project_id", "entity_identities.id"],
            name="fk_inventory_process_mappings_process",
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    source_id: Mapped[str] = mapped_column(identifier())
    alias: Mapped[str] = mapped_column(identifier())
    local_id: Mapped[str] = mapped_column(identifier())
    process_id: Mapped[str] = mapped_column(identifier())
    baseline: Mapped[dict] = mapped_column(JSON)
