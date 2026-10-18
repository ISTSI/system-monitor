"""Scoped static inventory reconciliation and short-lived sanitized preview bindings."""

from alembic import op

revision = "0013_inventory"
down_revision = "0012_offline_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "\nCREATE TABLE inventory_sources (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tname VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tname_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tcreated_us BIGINT NOT NULL, \n\tCONSTRAINT pk_inventory_sources PRIMARY KEY (project_id, id), \n\tCONSTRAINT uq_inventory_sources_name UNIQUE (project_id, name_key), \n\tCONSTRAINT fk_inventory_sources_project FOREIGN KEY(project_id) REFERENCES projects (id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute(
        "\nCREATE TABLE inventory_uploads (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tsource_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\texpected_revision INTEGER NOT NULL, \n\tfilename VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tdigest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tmanifest_digest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tsummary JSON NOT NULL, \n\texpires_us BIGINT NOT NULL, \n\tCONSTRAINT pk_inventory_uploads PRIMARY KEY (project_id, id), \n\tCONSTRAINT uq_inventory_uploads_owner_source UNIQUE (project_id, id, source_id, owner_user_id), \n\tCONSTRAINT fk_inventory_uploads_source FOREIGN KEY(project_id, source_id) REFERENCES inventory_sources (project_id, id), \n\tCONSTRAINT fk_inventory_uploads_owner FOREIGN KEY(owner_user_id) REFERENCES users (id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute("CREATE INDEX ix_inventory_uploads_expiry ON inventory_uploads (expires_us)")
    op.execute(
        "\nCREATE TABLE inventory_previews (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tsource_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tupload_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\texpected_revision INTEGER NOT NULL, \n\tcontent_digest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tmanifest_digest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tmapping_digest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tdigest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tdocument JSON NOT NULL, \n\texpires_us BIGINT NOT NULL, \n\tCONSTRAINT pk_inventory_previews PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_inventory_previews_upload_owner_source FOREIGN KEY(project_id, upload_id, source_id, owner_user_id) REFERENCES inventory_uploads (project_id, id, source_id, owner_user_id), \n\tCONSTRAINT fk_inventory_previews_source FOREIGN KEY(project_id, source_id) REFERENCES inventory_sources (project_id, id), \n\tCONSTRAINT fk_inventory_previews_owner FOREIGN KEY(owner_user_id) REFERENCES users (id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute("CREATE INDEX ix_inventory_previews_expiry ON inventory_previews (expires_us)")
    op.execute(
        "\nCREATE TABLE inventory_host_mappings (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tsource_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\talias VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tserver_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tconnection_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tbaseline JSON NOT NULL, \n\tCONSTRAINT pk_inventory_host_mappings PRIMARY KEY (project_id, source_id, alias), \n\tCONSTRAINT fk_inventory_host_mappings_source FOREIGN KEY(project_id, source_id) REFERENCES inventory_sources (project_id, id), \n\tCONSTRAINT fk_inventory_host_mappings_server FOREIGN KEY(project_id, server_id) REFERENCES entity_identities (project_id, id), \n\tCONSTRAINT fk_inventory_host_mappings_connection FOREIGN KEY(project_id, connection_id) REFERENCES entity_identities (project_id, id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute(
        "\nCREATE TABLE inventory_process_mappings (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tsource_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\talias VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tlocal_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tprocess_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tbaseline JSON NOT NULL, \n\tCONSTRAINT pk_inventory_process_mappings PRIMARY KEY (project_id, source_id, alias, local_id), \n\tCONSTRAINT fk_inventory_process_mappings_host FOREIGN KEY(project_id, source_id, alias) REFERENCES inventory_host_mappings (project_id, source_id, alias), \n\tCONSTRAINT fk_inventory_process_mappings_process FOREIGN KEY(project_id, process_id) REFERENCES entity_identities (project_id, id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )


def downgrade() -> None:
    op.drop_table("inventory_process_mappings")
    op.drop_table("inventory_host_mappings")
    op.drop_table("inventory_previews")
    op.drop_table("inventory_uploads")
    op.drop_table("inventory_sources")
