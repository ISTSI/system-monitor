import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from inspector.errors import DomainError

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"


def server_connection_id(server: Mapping[str, Any]) -> str:
    connection_id: str | None = server["connection_id"]
    if connection_id is None:
        raise DomainError(
            "SERVER_NOT_CONNECTED",
            "A selected server has no connection assigned. Assign a connection before collecting its logs.",
            409,
        )
    return connection_id


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    role: str
    auth_version: int
    must_change_password: bool = False
    display_name: str = ""
    username: str = ""


@dataclass(frozen=True, slots=True)
class ProjectContext:
    project_id: str
    user_id: str

    def __post_init__(self) -> None:
        if not re.fullmatch(ID_PATTERN, self.project_id) or not re.fullmatch(
            ID_PATTERN, self.user_id
        ):
            raise DomainError("INVALID_SCOPE", "Invalid project or owner identifier.", 422)
