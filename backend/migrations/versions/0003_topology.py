"""Stage 02 topology: frozen MariaDB DDL, scoped references and import/history state."""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_topology"
down_revision: str | Sequence[str] | None = "0002_foundation_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE topology_states (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tconfig JSON NOT NULL, \n\tundo_stack JSON NOT NULL, \n\tredo_stack JSON NOT NULL, \n\tCONSTRAINT pk_topology_states PRIMARY KEY (project_id), \n\tCONSTRAINT fk_topology_states_project FOREIGN KEY(project_id) REFERENCES projects (id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE topology_snapshots (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\trevision INTEGER NOT NULL, \n\tconfig JSON NOT NULL, \n\tCONSTRAINT pk_topology_snapshots PRIMARY KEY (project_id, revision), \n\tCONSTRAINT fk_topology_snapshots_revision FOREIGN KEY(project_id, revision) REFERENCES project_revisions (project_id, revision)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE entity_identities (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tkind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tname VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tdeleted BOOL NOT NULL, \n\tCONSTRAINT pk_entity_identities PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_entity_identities_project FOREIGN KEY(project_id) REFERENCES projects (id), \n\tCONSTRAINT ck_entity_identities_deleted CHECK (deleted IN (0, 1))\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE subsystems (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tname VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tname_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tpayload JSON NOT NULL, \n\tCONSTRAINT pk_subsystems PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_subsystems_identity FOREIGN KEY(project_id, id) REFERENCES entity_identities (project_id, id), \n\tCONSTRAINT uq_subsystems_project_name UNIQUE (project_id, name_key)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE connection_profiles (\n\tjump_connection_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin, \n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tname VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tname_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tpayload JSON NOT NULL, \n\tCONSTRAINT pk_connection_profiles PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_connections_scoped_jump FOREIGN KEY(project_id, jump_connection_id) REFERENCES connection_profiles (project_id, id), \n\tCONSTRAINT fk_connection_profiles_identity FOREIGN KEY(project_id, id) REFERENCES entity_identities (project_id, id), \n\tCONSTRAINT uq_connection_profiles_project_name UNIQUE (project_id, name_key)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE parser_profiles (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tname VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tname_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tpayload JSON NOT NULL, \n\tCONSTRAINT pk_parser_profiles PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_parser_profiles_identity FOREIGN KEY(project_id, id) REFERENCES entity_identities (project_id, id), \n\tCONSTRAINT uq_parser_profiles_project_name UNIQUE (project_id, name_key)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE servers (\n\tsubsystem_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tconnection_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tname VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tname_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tpayload JSON NOT NULL, \n\tCONSTRAINT pk_servers PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_servers_scoped_subsystem FOREIGN KEY(project_id, subsystem_id) REFERENCES subsystems (project_id, id), \n\tCONSTRAINT fk_servers_scoped_connection FOREIGN KEY(project_id, connection_id) REFERENCES connection_profiles (project_id, id), \n\tCONSTRAINT fk_servers_identity FOREIGN KEY(project_id, id) REFERENCES entity_identities (project_id, id), \n\tCONSTRAINT uq_servers_project_name UNIQUE (project_id, name_key)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE processes (\n\tserver_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tparser_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tname VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tname_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tpayload JSON NOT NULL, \n\tCONSTRAINT pk_processes PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_processes_scoped_server FOREIGN KEY(project_id, server_id) REFERENCES servers (project_id, id), \n\tCONSTRAINT fk_processes_scoped_parser FOREIGN KEY(project_id, parser_id) REFERENCES parser_profiles (project_id, id), \n\tCONSTRAINT fk_processes_identity FOREIGN KEY(project_id, id) REFERENCES entity_identities (project_id, id), \n\tCONSTRAINT uq_processes_project_name UNIQUE (project_id, name_key)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE flows (\n\tsource_process_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\ttarget_process_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tname VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tname_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tpayload JSON NOT NULL, \n\tCONSTRAINT pk_flows PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_flows_scoped_source FOREIGN KEY(project_id, source_process_id) REFERENCES processes (project_id, id), \n\tCONSTRAINT fk_flows_scoped_target FOREIGN KEY(project_id, target_process_id) REFERENCES processes (project_id, id), \n\tCONSTRAINT fk_flows_identity FOREIGN KEY(project_id, id) REFERENCES entity_identities (project_id, id), \n\tCONSTRAINT uq_flows_project_name UNIQUE (project_id, name_key)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE shared_views (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tname VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tname_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tpayload JSON NOT NULL, \n\tCONSTRAINT pk_shared_views PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_shared_views_identity FOREIGN KEY(project_id, id) REFERENCES entity_identities (project_id, id), \n\tCONSTRAINT uq_shared_views_project_name UNIQUE (project_id, name_key)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE view_nodes (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tview_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\telement_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tgeometry JSON NOT NULL, \n\tCONSTRAINT pk_view_nodes PRIMARY KEY (project_id, view_id, element_id), \n\tCONSTRAINT fk_view_nodes_scoped_view FOREIGN KEY(project_id, view_id) REFERENCES shared_views (project_id, id), \n\tCONSTRAINT fk_view_nodes_scoped_element FOREIGN KEY(project_id, element_id) REFERENCES entity_identities (project_id, id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE view_flows (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tview_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tflow_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tCONSTRAINT pk_view_flows PRIMARY KEY (project_id, view_id, flow_id), \n\tCONSTRAINT fk_view_flows_scoped_view FOREIGN KEY(project_id, view_id) REFERENCES shared_views (project_id, id), \n\tCONSTRAINT fk_view_flows_scoped_flow FOREIGN KEY(project_id, flow_id) REFERENCES flows (project_id, id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE TABLE config_previews (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\texpected_revision INTEGER NOT NULL, \n\tsource_project_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tdigest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tconfig JSON NOT NULL, \n\texpires_us BIGINT NOT NULL, \n\tCONSTRAINT pk_config_previews PRIMARY KEY (project_id, id), \n\tCONSTRAINT fk_config_previews_owner FOREIGN KEY(owner_user_id) REFERENCES users (id), \n\tCONSTRAINT fk_config_previews_revision FOREIGN KEY(project_id, expected_revision) REFERENCES project_revisions (project_id, revision)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )
    op.execute(
        "CREATE INDEX ix_config_previews_project_owner_expiry ON config_previews (project_id, owner_user_id, expires_us)"
    )


def downgrade() -> None:
    op.drop_table("config_previews")
    op.drop_table("view_flows")
    op.drop_table("view_nodes")
    op.drop_table("shared_views")
    op.drop_table("flows")
    op.drop_table("processes")
    op.drop_table("servers")
    op.drop_table("parser_profiles")
    op.drop_table("connection_profiles")
    op.drop_table("subsystems")
    op.drop_table("entity_identities")
    op.drop_table("topology_snapshots")
    op.drop_table("topology_states")
