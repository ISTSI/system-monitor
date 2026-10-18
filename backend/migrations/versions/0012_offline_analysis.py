"""Separate mutable private analysis from immutable imported bundle evidence."""

from alembic import op

revision = "0012_offline_analysis"
down_revision = "0011_investigation_bundles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "\nCREATE TABLE offline_analysis (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tinvestigation_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\trevision INTEGER NOT NULL, \n\tstate JSON NOT NULL, \n\tbookmarks JSON NOT NULL, \n\tCONSTRAINT pk_offline_analysis PRIMARY KEY (project_id, investigation_id), \n\tCONSTRAINT fk_offline_analysis_owner FOREIGN KEY(project_id, investigation_id, owner_user_id) REFERENCES offline_investigations (project_id, id, owner_user_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )


def downgrade() -> None:
    op.drop_table("offline_analysis")
