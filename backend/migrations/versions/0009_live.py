"""Stage 05 scoped live leases and atomic subscription reservations."""

from alembic import op

revision = "0009_live"
down_revision = "0008_security_setting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "\nCREATE TABLE live_sessions (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tworkspace_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\tauth_session_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tconfig_revision INTEGER NOT NULL, \n\tconfig_snapshot JSON NOT NULL, \n\tprocess_ids JSON NOT NULL, \n\tlease_revision INTEGER NOT NULL, \n\tfilter_version INTEGER NOT NULL, \n\tstatus VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tview JSON NOT NULL, \n\trecording BOOL NOT NULL, \n\tinvestigation_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin, \n\tcreated_us BIGINT NOT NULL, \n\tdetached_until_us BIGINT, \n\terror_code VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin, \n\tCONSTRAINT pk_live_sessions PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_live_sessions_workspace_owner FOREIGN KEY(project_id, workspace_id, owner_user_id) REFERENCES workspaces (project_id, id, owner_user_id), \n\tCONSTRAINT fk_live_sessions_revision FOREIGN KEY(project_id, config_revision) REFERENCES project_revisions (project_id, revision), \n\tCONSTRAINT fk_live_sessions_recording_owner FOREIGN KEY(project_id, investigation_id, owner_user_id) REFERENCES history_jobs (project_id, id, owner_user_id), \n\tCONSTRAINT uq_live_sessions_owner UNIQUE (project_id, id, owner_user_id), \n\tCONSTRAINT ck_live_sessions_versions CHECK (lease_revision >= 1 AND filter_version >= 1), \n\tCONSTRAINT ck_live_sessions_recording CHECK (recording IN (0, 1))\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute("CREATE INDEX ix_live_sessions_owner_state ON live_sessions (owner_user_id, status)")
    op.execute(
        "CREATE INDEX ix_live_sessions_workspace ON live_sessions (project_id, workspace_id, status)"
    )
    op.execute(
        "\nCREATE TABLE live_subscriptions (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tsession_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tprocess_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tprocess_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tCONSTRAINT pk_live_subscriptions PRIMARY KEY (project_id, session_id, process_id), \n\tCONSTRAINT fk_live_subscriptions_session_owner FOREIGN KEY(project_id, session_id, owner_user_id) REFERENCES live_sessions (project_id, id, owner_user_id), \n\tCONSTRAINT fk_live_subscriptions_process FOREIGN KEY(project_id, process_id, process_kind) REFERENCES entity_identities (project_id, id, kind), \n\tCONSTRAINT ck_live_subscriptions_process_kind CHECK (process_kind = 'process')\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute("CREATE INDEX ix_live_subscriptions_owner ON live_subscriptions (owner_user_id)")


def downgrade() -> None:
    op.drop_table("live_subscriptions")
    op.drop_table("live_sessions")
