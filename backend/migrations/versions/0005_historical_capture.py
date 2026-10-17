"""Project/owner-bound historical captures and snapshot cursors."""

from alembic import op

revision = "0005_historical_capture"
down_revision = "0004_topology_name_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_entity_identities_kind", "entity_identities", ["project_id", "id", "kind"]
    )
    op.execute(
        "\nCREATE TABLE history_jobs (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tworkspace_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\tauth_session_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tconfig_revision INTEGER NOT NULL, \n\tconfig_snapshot JSON NOT NULL, \n\tprocess_ids JSON NOT NULL, \n\tfrom_us BIGINT NOT NULL, \n\tto_us BIGINT NOT NULL, \n\tstatus VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tsnapshot_revision BIGINT NOT NULL, \n\tevent_count BIGINT NOT NULL, \n\tparse_issue_count BIGINT NOT NULL, \n\tdownloaded_bytes BIGINT NOT NULL, \n\texpanded_bytes BIGINT NOT NULL, \n\tcreated_us BIGINT NOT NULL, \n\terrors JSON NOT NULL, \n\tCONSTRAINT pk_history_jobs PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_history_jobs_scoped_workspace_owner FOREIGN KEY(project_id, workspace_id, owner_user_id) REFERENCES workspaces (project_id, id, owner_user_id), \n\tCONSTRAINT fk_history_jobs_scoped_revision FOREIGN KEY(project_id, config_revision) REFERENCES project_revisions (project_id, revision), \n\tCONSTRAINT uq_history_jobs_owner UNIQUE (project_id, id, owner_user_id), \n\tCONSTRAINT ck_history_jobs_counts CHECK (snapshot_revision >= 0 AND event_count >= 0)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute("CREATE INDEX ix_history_jobs_owner_state ON history_jobs (owner_user_id, status)")
    op.execute(
        "\nCREATE TABLE history_sources (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tjob_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tprocess_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tprocess_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'process', \n\tremote_path TEXT NOT NULL, \n\tkind VARCHAR(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tcache_name VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tchecksum VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin, \n\tstatus VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\terror_code VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin, \n\tevent_count BIGINT NOT NULL, \n\tdownloaded_bytes BIGINT NOT NULL, \n\texpanded_bytes BIGINT NOT NULL, \n\tmanifest JSON NOT NULL, \n\tCONSTRAINT pk_history_sources PRIMARY KEY (project_id, job_id, id), \n\tCONSTRAINT fk_history_sources_scoped_job FOREIGN KEY(project_id, job_id) REFERENCES history_jobs (project_id, id), \n\tCONSTRAINT fk_history_sources_scoped_process FOREIGN KEY(project_id, process_id, process_kind) REFERENCES entity_identities (project_id, id, kind), \n\tCONSTRAINT ck_history_sources_process_kind CHECK (process_kind = 'process'), \n\tCONSTRAINT uq_history_sources_process UNIQUE (project_id, job_id, id, process_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute(
        "\nCREATE TABLE history_events (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tjob_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tevent_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tprocess_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tsource_revision_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tcapture_seq BIGINT NOT NULL, \n\ttimestamp_us BIGINT, \n\tmember_order INTEGER NOT NULL, \n\tbyte_start BIGINT NOT NULL, \n\traw_line LONGTEXT NOT NULL, \n\tpayload JSON NOT NULL, \n\tCONSTRAINT pk_history_events PRIMARY KEY (project_id, job_id, event_id), \n\tCONSTRAINT fk_history_events_scoped_source FOREIGN KEY(project_id, job_id, source_revision_id, process_id) REFERENCES history_sources (project_id, job_id, id, process_id), \n\tCONSTRAINT uq_history_events_seq UNIQUE (project_id, job_id, capture_seq)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute(
        "CREATE INDEX ix_history_events_order ON history_events (project_id, job_id, timestamp_us, process_id, source_revision_id, member_order, byte_start, event_id)"
    )
    op.execute(
        "CREATE INDEX ix_history_events_source_order ON history_events (project_id, job_id, source_revision_id, member_order, byte_start)"
    )
    op.execute(
        "\nCREATE TABLE history_cursors (\n\ttoken_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tjob_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\tquery_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tsnapshot_revision BIGINT NOT NULL, \n\tmax_seq BIGINT NOT NULL, \n\tafter_key JSON NOT NULL, \n\texpires_us BIGINT NOT NULL, \n\tCONSTRAINT pk_history_cursors PRIMARY KEY (token_hash), \n\tCONSTRAINT fk_history_cursors_scoped_owner_job FOREIGN KEY(project_id, job_id, owner_user_id) REFERENCES history_jobs (project_id, id, owner_user_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute("CREATE INDEX ix_history_cursors_expiry ON history_cursors (expires_us)")
    op.execute(
        "\nCREATE TABLE history_downloads (\n\ttoken_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tjob_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tsource_revision_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\texpires_us BIGINT NOT NULL, \n\tCONSTRAINT pk_history_downloads PRIMARY KEY (token_hash), \n\tCONSTRAINT fk_history_downloads_scoped_source FOREIGN KEY(project_id, job_id, source_revision_id) REFERENCES history_sources (project_id, job_id, id), \n\tCONSTRAINT fk_history_downloads_scoped_owner_job FOREIGN KEY(project_id, job_id, owner_user_id) REFERENCES history_jobs (project_id, id, owner_user_id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute("CREATE INDEX ix_history_downloads_expiry ON history_downloads (expires_us)")


def downgrade() -> None:
    op.drop_table("history_downloads")
    op.drop_table("history_cursors")
    op.drop_table("history_events")
    op.drop_table("history_sources")
    op.drop_table("history_jobs")
    op.drop_constraint("uq_entity_identities_kind", "entity_identities", type_="unique")
