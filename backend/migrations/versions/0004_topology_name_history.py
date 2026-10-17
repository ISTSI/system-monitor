"""Preserve compact historical entity names independently of bounded undo snapshots."""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_topology_name_history"
down_revision: str | Sequence[str] | None = "0003_topology"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE topology_entity_names (\n\tproject_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\tid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, \n\trevision INTEGER NOT NULL, \n\tname VARCHAR(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, \n\tdeleted BOOL NOT NULL, \n\tCONSTRAINT pk_topology_entity_names PRIMARY KEY (project_id, id, revision), \n\tCONSTRAINT fk_topology_entity_names_identity FOREIGN KEY(project_id, id) REFERENCES entity_identities (project_id, id), \n\tCONSTRAINT fk_topology_entity_names_revision FOREIGN KEY(project_id, revision) REFERENCES project_revisions (project_id, revision), \n\tCONSTRAINT ck_topology_entity_names_deleted CHECK (deleted IN (0, 1))\n)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin"
    )

    _backfill_names()


def _backfill_names() -> None:
    bind = op.get_bind()
    insert_name = sa.text(
        "INSERT INTO topology_entity_names (project_id,id,revision,name,deleted) VALUES (:project_id,:id,:revision,:name,:deleted)"
    )
    previous: dict[tuple[str, str], str] = {}
    snapshots = bind.execute(
        sa.text(
            "SELECT project_id,revision,config FROM topology_snapshots ORDER BY project_id,revision"
        )
    )
    for row in snapshots:
        config = json.loads(row.config) if isinstance(row.config, str) else row.config
        names = {
            item["id"]: item["name"]
            for collection in (
                "subsystems",
                "connections",
                "parsers",
                "servers",
                "processes",
                "flows",
                "views",
            )
            for item in config[collection]
        }
        for identifier, name in names.items():
            key = (row.project_id, identifier)
            if previous.get(key) != name:
                bind.execute(
                    insert_name,
                    dict(
                        project_id=row.project_id,
                        id=identifier,
                        revision=row.revision,
                        name=name,
                        deleted=False,
                    ),
                )
                previous[key] = name
        removed = [
            (key, name)
            for key, name in previous.items()
            if key[0] == row.project_id and key[1] not in names
        ]
        for key, name in removed:
            bind.execute(
                insert_name,
                dict(
                    project_id=row.project_id,
                    id=key[1],
                    revision=row.revision,
                    name=name,
                    deleted=True,
                ),
            )
            del previous[key]
    # A deleted identity may predate retained full snapshots; preserve its last
    # known name at its verified current project's revision as a tombstone.
    bind.execute(
        sa.text(
            "INSERT IGNORE INTO topology_entity_names (project_id,id,revision,name,deleted) SELECT e.project_id,e.id,p.revision,e.name,e.deleted FROM entity_identities e JOIN projects p ON p.id=e.project_id WHERE NOT EXISTS (SELECT 1 FROM topology_entity_names n WHERE n.project_id=e.project_id AND n.id=e.id)"
        )
    )


def downgrade() -> None:
    op.drop_table("topology_entity_names")
