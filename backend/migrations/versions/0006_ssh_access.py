"""Encrypted SSH passwords, explicit project bindings and host-key trust."""

from alembic import op

revision = "0006_ssh_access"
down_revision = "0005_historical_capture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "\nCREATE TABLE ssh_credentials (\n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\trevision INTEGER NOT NULL, \n\tkey_version INTEGER NOT NULL, \n\tnonce VARBINARY(12) NOT NULL, \n\tciphertext VARBINARY(1040) NOT NULL, \n\tCONSTRAINT pk_ssh_credentials PRIMARY KEY (id), \n\tCONSTRAINT ck_ssh_credentials_versions CHECK (revision >= 1 AND key_version >= 1)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute(
        "\nCREATE TABLE project_credential_bindings (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\talias VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tcredential_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tCONSTRAINT pk_project_credential_bindings PRIMARY KEY (project_id, alias), \n\tCONSTRAINT fk_credential_binding_project FOREIGN KEY(project_id) REFERENCES projects (id), \n\tCONSTRAINT fk_credential_binding_vault FOREIGN KEY(credential_id) REFERENCES ssh_credentials (id)\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute(
        "\nCREATE TABLE ssh_host_trust (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tconnection_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tconnection_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\trevision INTEGER NOT NULL, \n\tapproved BOOL NOT NULL, \n\troute_digest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tpublic_key VARCHAR(8192) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\talgorithm VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tfingerprint VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tCONSTRAINT pk_ssh_host_trust PRIMARY KEY (project_id, connection_id), \n\tCONSTRAINT fk_ssh_host_trust_scoped_connection FOREIGN KEY(project_id, connection_id, connection_kind) REFERENCES entity_identities (project_id, id, kind), \n\tCONSTRAINT ck_ssh_host_trust_connection_kind CHECK (connection_kind = 'connection'), \n\tCONSTRAINT ck_ssh_host_trust_revision CHECK (revision >= 1), \n\tCONSTRAINT ck_ssh_host_trust_approved CHECK (approved IN (0, 1))\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute(
        "\nCREATE TABLE ssh_key_inspections (\n\ttoken_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tconnection_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tconnection_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\towner_user_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tauth_version INTEGER NOT NULL, \n\tauth_session_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\ttrust_revision INTEGER NOT NULL, \n\tconfig_revision INTEGER NOT NULL, \n\troute_digest VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tnetwork_signature VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tpublic_key VARCHAR(8192) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\talgorithm VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tfingerprint VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\texpires_us BIGINT NOT NULL, \n\tCONSTRAINT pk_ssh_key_inspections PRIMARY KEY (token_hash), \n\tCONSTRAINT fk_ssh_inspection_scoped_connection FOREIGN KEY(project_id, connection_id, connection_kind) REFERENCES entity_identities (project_id, id, kind), \n\tCONSTRAINT fk_ssh_inspection_owner FOREIGN KEY(owner_user_id) REFERENCES users (id), \n\tCONSTRAINT fk_ssh_inspection_revision FOREIGN KEY(project_id, config_revision) REFERENCES project_revisions (project_id, revision), \n\tCONSTRAINT ck_ssh_key_inspections_connection_kind CHECK (connection_kind = 'connection')\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin\n\n"
    )
    op.execute("CREATE INDEX ix_ssh_inspections_expiry ON ssh_key_inspections (expires_us)")


def downgrade() -> None:
    op.drop_table("ssh_key_inspections")
    op.drop_table("ssh_host_trust")
    op.drop_table("project_credential_bindings")
    op.drop_table("ssh_credentials")
