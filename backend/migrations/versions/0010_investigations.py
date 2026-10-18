"""Saved private analysis and pinned context, without changing source identity."""

from alembic import op

revision = "0010_investigations"
down_revision = "0009_live"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "\nCREATE TABLE saved_investigations (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tjob_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\trevision INTEGER NOT NULL, \n\tstate JSON NOT NULL, \n\tpinned BOOL NOT NULL, \n\texpired BOOL NOT NULL, \n\tupdated_us BIGINT NOT NULL, \n\tCONSTRAINT pk_saved_investigations PRIMARY KEY (project_id, job_id), \n\tCONSTRAINT fk_saved_investigation_owner FOREIGN KEY(project_id, job_id, owner_user_id) REFERENCES history_jobs (project_id, id, owner_user_id), \n\tCONSTRAINT ck_saved_investigations_revision CHECK (revision >= 1), \n\tCONSTRAINT ck_saved_investigations_flags CHECK (pinned IN (0,1) AND expired IN (0,1))\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute(
        "\nCREATE TABLE investigation_bookmarks (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tjob_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tevent_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\treference_event_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin, \n\tannotation TEXT NOT NULL, \n\tpin_context BOOL NOT NULL, \n\tcontext JSON NOT NULL, \n\tprocess_name_snapshot VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tserver_name_snapshot VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tcreated_us BIGINT NOT NULL, \n\tCONSTRAINT pk_investigation_bookmarks PRIMARY KEY (project_id, job_id, id), \n\tCONSTRAINT fk_investigation_bookmark_owner FOREIGN KEY(project_id, job_id, owner_user_id) REFERENCES history_jobs (project_id, id, owner_user_id), \n\tCONSTRAINT fk_investigation_bookmark_event FOREIGN KEY(project_id, job_id, reference_event_id) REFERENCES history_events (project_id, job_id, event_id), \n\tCONSTRAINT ck_investigation_bookmarks_pin CHECK (pin_context IN (0,1))\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )


def downgrade() -> None:
    op.drop_table("investigation_bookmarks")
    op.drop_table("saved_investigations")
