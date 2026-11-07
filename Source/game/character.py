from dataclasses import dataclass
from enum import Enum

class Status(Enum):
    """Trạng thái thật của nhân vật"""
    CRIMINAL = "CRIMINAL"
    INNOCENT = "INNOCENT"

    @property
    def opposite(self) -> "Status":
        """Trả về trạng thái đối nghịch với trạng thái thật"""
        return Status.INNOCENT if self is Status.CRIMINAL else Status.CRIMINAL


@dataclass(frozen=True)
class Character:
    """Thông tin công khai của một nhân vật."""
    name: str
    profession: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("[Character]: Tên nhân vật không được rỗng")

    def __str__(self) -> str:
        """Trả về tên nhân vật"""
        return self.name
    