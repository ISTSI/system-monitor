"""Private saved analysis and independently retained context snapshots."""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from inspector.persistence.models import TABLE_OPTIONS, Base, binary_text, identifier


class SavedInvestigation(Base):
    __tablename__ = "saved_investigations"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "job_id"),
        ForeignKeyConstraint(
            ["project_id", "job_id", "owner_user_id"],
            ["history_jobs.project_id", "history_jobs.id", "history_jobs.owner_user_id"],
            name="fk_saved_investigation_owner",
        ),
        CheckConstraint("revision >= 1", name="revision"),
        CheckConstraint("pinned IN (0,1) AND expired IN (0,1)", name="flags"),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    job_id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict] = mapped_column(JSON)
    pinned: Mapped[bool] = mapped_column(Boolean)
    expired: Mapped[bool] = mapped_column(Boolean)
    updated_us: Mapped[int] = mapped_column(BigInteger)


class InvestigationBookmark(Base):
    __tablename__ = "investigation_bookmarks"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "job_id", "id"),
        ForeignKeyConstraint(
            ["project_id", "job_id", "owner_user_id"],
            ["history_jobs.project_id", "history_jobs.id", "history_jobs.owner_user_id"],
            name="fk_investigation_bookmark_owner",
        ),
        ForeignKeyConstraint(
            ["project_id", "job_id", "reference_event_id"],
            ["history_events.project_id", "history_events.job_id", "history_events.event_id"],
            name="fk_investigation_bookmark_event",
        ),
        CheckConstraint("pin_context IN (0,1)", name="pin"),
        TABLE_OPTIONS,
    )
    project_id: Mapped[str] = mapped_column(identifier())
    job_id: Mapped[str] = mapped_column(identifier())
    id: Mapped[str] = mapped_column(identifier())
    owner_user_id: Mapped[str] = mapped_column(identifier())
    event_id: Mapped[str] = mapped_column(identifier())
    reference_event_id: Mapped[str | None] = mapped_column(identifier(), nullable=True)
    annotation: Mapped[str] = mapped_column(Text)
    pin_context: Mapped[bool] = mapped_column(Boolean)
    context: Mapped[dict] = mapped_column(JSON)
    process_name_snapshot: Mapped[str] = mapped_column(binary_text(256))
    server_name_snapshot: Mapped[str] = mapped_column(binary_text(256))
    created_us: Mapped[int] = mapped_column(BigInteger)
