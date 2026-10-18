"""Stage 06 private sanitized bundle previews, grants and offline data."""

from alembic import op

revision = "0011_investigation_bundles"
down_revision = "0010_investigations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "\nCREATE TABLE bundle_previews (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\tauth_session_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tdirection VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tsource_job_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin, \n\tproject_revision INTEGER NOT NULL, \n\tcontent_revision VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tdigest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tdocument JSON NOT NULL, \n\tcreated_us BIGINT NOT NULL, \n\texpires_us BIGINT NOT NULL, \n\tCONSTRAINT pk_bundle_previews PRIMARY KEY (project_id, id), \n\tCONSTRAINT uq_bundle_previews_owner UNIQUE (project_id, id, owner_user_id), \n\tCONSTRAINT fk_bundle_previews_project FOREIGN KEY(project_id) REFERENCES projects (id), \n\tCONSTRAINT fk_bundle_previews_owner FOREIGN KEY(owner_user_id) REFERENCES users (id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute(
        "CREATE INDEX ix_bundle_previews_project_owner_expiry ON bundle_previews (project_id, owner_user_id, expires_us)"
    )
    op.execute(
        "\nCREATE TABLE bundle_downloads (\n\ttoken_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tpreview_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\tauth_session_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\texpires_us BIGINT NOT NULL, \n\tCONSTRAINT pk_bundle_downloads PRIMARY KEY (token_hash), \n\tCONSTRAINT fk_bundle_downloads_preview FOREIGN KEY(project_id, preview_id, owner_user_id) REFERENCES bundle_previews (project_id, id, owner_user_id), \n\tCONSTRAINT fk_bundle_downloads_owner FOREIGN KEY(owner_user_id) REFERENCES users (id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute("CREATE INDEX ix_bundle_downloads_expiry ON bundle_downloads (expires_us)")
    op.execute(
        "\nCREATE TABLE offline_investigations (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tdigest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tdocument JSON NOT NULL, \n\tcreated_us BIGINT NOT NULL, \n\tCONSTRAINT pk_offline_investigations PRIMARY KEY (project_id, id), \n\tCONSTRAINT uq_offline_investigations_owner UNIQUE (project_id, id, owner_user_id), \n\tCONSTRAINT fk_offline_investigations_project FOREIGN KEY(project_id) REFERENCES projects (id), \n\tCONSTRAINT fk_offline_investigations_owner FOREIGN KEY(owner_user_id) REFERENCES users (id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute(
        "CREATE INDEX ix_offline_investigations_project_owner ON offline_investigations (project_id, owner_user_id, created_us)"
    )
    op.execute(
        "\nCREATE TABLE offline_cursors (\n\ttoken_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tinvestigation_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\tquery_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\trow_offset BIGINT NOT NULL, \n\texpires_us BIGINT NOT NULL, \n\tCONSTRAINT pk_offline_cursors PRIMARY KEY (token_hash), \n\tCONSTRAINT fk_offline_cursors_investigation FOREIGN KEY(project_id, investigation_id, owner_user_id) REFERENCES offline_investigations (project_id, id, owner_user_id), \n\tCONSTRAINT fk_offline_cursors_owner FOREIGN KEY(owner_user_id) REFERENCES users (id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute("CREATE INDEX ix_offline_cursors_expiry ON offline_cursors (expires_us)")


def downgrade() -> None:
    op.drop_table("offline_cursors")
    op.drop_table("offline_investigations")
    op.drop_table("bundle_downloads")
    op.drop_table("bundle_previews")
