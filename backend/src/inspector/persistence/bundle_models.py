"""Private offline exchange; foreign identities never reference active topology."""

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

from inspector.persistence.models import TABLE_OPTIONS, Base, identifier, verifier


class BundlePreview(Base):
    __tablename__ = "bundle_previews"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", name="pk_bundle_previews"),
        UniqueConstraint("project_id", "id", "owner_user_id", name="uq_bundle_previews_owner"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_bundle_previews_project"),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_bundle_previews_owner"),
        Index(
            "ix_bundle_previews_project_owner_expiry", "project_id", "owner_user_id", "expires_us"
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    auth_version: Mapped[int] = mapped_column(Integer)
    auth_session_hash: Mapped[str] = mapped_column(verifier())
    direction: Mapped[str] = mapped_column(identifier())
    source_job_id: Mapped[str | None] = mapped_column(identifier(), nullable=True)
    project_revision: Mapped[int] = mapped_column(Integer)
    content_revision: Mapped[str] = mapped_column(verifier())
    digest: Mapped[str] = mapped_column(verifier())
    document: Mapped[dict] = mapped_column(JSON)
    created_us: Mapped[int] = mapped_column(BigInteger)
    expires_us: Mapped[int] = mapped_column(BigInteger)


class BundleDownload(Base):
    __tablename__ = "bundle_downloads"
    __table_args__ = (
        PrimaryKeyConstraint("token_hash", name="pk_bundle_downloads"),
        ForeignKeyConstraint(
            ["project_id", "preview_id", "owner_user_id"],
            ["bundle_previews.project_id", "bundle_previews.id", "bundle_previews.owner_user_id"],
            name="fk_bundle_downloads_preview",
        ),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_bundle_downloads_owner"),
        Index("ix_bundle_downloads_expiry", "expires_us"),
        TABLE_OPTIONS,
    )
    token_hash: Mapped[str] = mapped_column(verifier())
    project_id: Mapped[str] = mapped_column(identifier())
    preview_id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    auth_version: Mapped[int] = mapped_column(Integer)
    auth_session_hash: Mapped[str] = mapped_column(verifier())
    expires_us: Mapped[int] = mapped_column(BigInteger)


class OfflineInvestigation(Base):
    __tablename__ = "offline_investigations"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", name="pk_offline_investigations"),
        UniqueConstraint(
            "project_id", "id", "owner_user_id", name="uq_offline_investigations_owner"
        ),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_offline_investigations_project"
        ),
        ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name="fk_offline_investigations_owner"
        ),
        Index(
            "ix_offline_investigations_project_owner", "project_id", "owner_user_id", "created_us"
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    digest: Mapped[str] = mapped_column(verifier())
    document: Mapped[dict] = mapped_column(JSON)
    created_us: Mapped[int] = mapped_column(BigInteger)


class OfflineCursor(Base):
    __tablename__ = "offline_cursors"
    __table_args__ = (
        PrimaryKeyConstraint("token_hash", name="pk_offline_cursors"),
        ForeignKeyConstraint(
            ["project_id", "investigation_id", "owner_user_id"],
            [
                "offline_investigations.project_id",
                "offline_investigations.id",
                "offline_investigations.owner_user_id",
            ],
            name="fk_offline_cursors_investigation",
        ),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_offline_cursors_owner"),
        Index("ix_offline_cursors_expiry", "expires_us"),
        TABLE_OPTIONS,
    )
    token_hash: Mapped[str] = mapped_column(verifier())
    project_id: Mapped[str] = mapped_column(identifier())
    investigation_id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    auth_version: Mapped[int] = mapped_column(Integer)
    query_hash: Mapped[str] = mapped_column(verifier())
    row_offset: Mapped[int] = mapped_column(BigInteger)
    expires_us: Mapped[int] = mapped_column(BigInteger)


class OfflineAnalysis(Base):
    """Mutable personal analysis kept apart from immutable imported evidence."""

    __tablename__ = "offline_analysis"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "investigation_id", name="pk_offline_analysis"),
        ForeignKeyConstraint(
            ["project_id", "investigation_id", "owner_user_id"],
            [
                "offline_investigations.project_id",
                "offline_investigations.id",
                "offline_investigations.owner_user_id",
            ],
            name="fk_offline_analysis_owner",
        ),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    investigation_id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict] = mapped_column(JSON)
    bookmarks: Mapped[list] = mapped_column(JSON)
