import re
from dataclasses import dataclass

from inspector.errors import DomainError

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"


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
