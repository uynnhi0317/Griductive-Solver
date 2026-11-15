from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping

from .board import Board
from .cell import Cell


class Region(ABC):
    """Định nghĩa region: row, column, neighbor, explicit cells"""

    @abstractmethod
    def cells(self, board: Board) -> tuple[Cell, ...]:
        """Lấy danh sách ô thuộc vùng"""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Chuyển vùng thành dict để lưu vào JSON"""

    @abstractmethod
    def describe(self, board: Board | None = None) -> str:
        """Mô tả của vùng để hiển thị"""

def join_names(names: list[str]) -> str:
    """Nối danh sách tên: 'A', 'A and B', 'A, B and C'"""
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def possessive(name: str) -> str:
    """Sở hữu cách: Eve -> Eve's, James -> James'"""
    return f"{name}'" if name.endswith("s") else f"{name}'s"


@dataclass(frozen=True)
class Row(Region):
    """Một hàng"""
    number: int

    def __post_init__(self) -> None:
        if not isinstance(self.number, int):
            raise ValueError(f"[Row]: Số hàng không hợp lệ: {self.number!r}")

    def cells(self, board: Board) -> tuple[Cell, ...]:
        return board.row_cells(self.number)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "ROW", "number": self.number}

    def describe(self, board: Board | None = None) -> str:
        return f"row {self.number}"


@dataclass(frozen=True)
class Column(Region):
    """Một cột"""
    letter: str

    def __post_init__(self) -> None:
        if not (isinstance(self.letter, str) and len(self.letter) == 1):
            raise ValueError(f"[Column]: Nhãn cột không hợp lệ: {self.letter!r}")

    def cells(self, board: Board) -> tuple[Cell, ...]:
        return board.column_cells(ord(self.letter) - ord("A") + 1)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "COLUMN", "letter": self.letter}

    def describe(self, board: Board | None = None) -> str:
        return f"column {self.letter}"


@dataclass(frozen=True)
class Neighbors(Region):
    """Các ô kề của một ô"""
    center: Cell

    def cells(self, board: Board) -> tuple[Cell, ...]:
        return board.neighbor_cells(self.center)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "NEIGHBORS", "cell": self.center.label}

    def describe(self, board: Board | None = None) -> str:
        if board is None:
            return f"neighbors of {self.center.label}"
        return f"{possessive(board.character_at(self.center).name)} neighbors"


@dataclass(frozen=True)
class ExplicitList(Region):
    """
    Tập người được chỉ định trực tiếp, dùng đúng một trong hai cách:
    + members:    danh sách ô cụ thể                       (JSON: "cells": ["A1", "C3"])
    + profession: mọi nhân vật làm nghề này trên board     (JSON: "profession": "Cop")
                  plural là dạng số nhiều để hiển thị      (mặc định thêm "s", JSON tuỳ chọn: "plural": "Police")
    """
    members: tuple[Cell, ...] = ()
    profession: str | None = None
    plural: str | None = None

    def __post_init__(self) -> None:
        if self.profession is not None:
            if self.members:
                raise ValueError("[ExplicitList]: Chỉ dùng một trong hai: danh sách ô hoặc nghề")
            if not isinstance(self.profession, str) or not self.profession.strip():
                raise ValueError(f"[ExplicitList]: Tên nghề không hợp lệ: {self.profession!r}")
            if self.plural is not None and (not isinstance(self.plural, str) or not self.plural.strip()):
                raise ValueError(f"[ExplicitList]: Dạng số nhiều không hợp lệ: {self.plural!r}")
            return

        if self.plural is not None:
            raise ValueError("[ExplicitList]: 'plural' chỉ dùng cùng 'profession'")
        if not self.members:
            raise ValueError("[ExplicitList]: Vùng không được rỗng")
        if not all(isinstance(c, Cell) for c in self.members):
            raise ValueError("[ExplicitList]: Các phần tử phải là Cell")
        if len(set(self.members)) != len(self.members):
            raise ValueError("[ExplicitList]: Các ô trong vùng phải phân biệt")
        object.__setattr__(self, "members", tuple(sorted(self.members)))

    @property
    def is_profession(self) -> bool:
        """Vùng được chọn theo nghề"""
        return self.profession is not None

    def cells(self, board: Board) -> tuple[Cell, ...]:
        if self.profession is not None:
            cells = board.cells_with_profession(self.profession)
            if not cells:
                raise ValueError(f"[ExplicitList]: Không có nhân vật nào làm nghề {self.profession!r}")
            return cells
        for c in self.members:
            if not board.contains(c):
                raise ValueError(f"[ExplicitList]: Ô {c.label} ngoài board")
        return self.members

    def profession_name(self, board: Board) -> str:
        """Tên nghề số ít"""
        if self.profession is None:
            raise ValueError("[ExplicitList]: Vùng không chọn theo nghề")
        return board.character_at(self.cells(board)[0]).profession

    def profession_plural(self, board: Board) -> str:
        """Tên nghề số nhiều để hiển thị"""
        return self.plural or self.profession_name(board) + "s"

    def to_dict(self) -> dict[str, Any]:
        if self.profession is not None:
            data: dict[str, Any] = {"type": "CELLS", "profession": self.profession}
            if self.plural is not None:
                data["plural"] = self.plural
            return data
        return {"type": "CELLS", "cells": [c.label for c in self.members]}

    def describe(self, board: Board | None = None) -> str:
        if self.profession is not None:
            if board is None:
                return f"profession {self.profession}"
            return f"the {self.profession_plural(board)}"
        if board is None:
            return "cells " + ", ".join(c.label for c in self.members)
        return join_names([board.character_at(c).name for c in self.members])


def _require(data: Mapping[str, Any], kind: str, *fields: str) -> None:
    """Kiểm tra thiếu trường dữ liệu"""
    for f in fields:
        if f not in data:
            raise ValueError(f"[{kind}]: Thiếu trường '{f}'")
        

def region_from_dict(data: Mapping[str, Any]) -> Region:
    """Tạo Region từ dict cho puzzle_loader"""
    if "type" not in data:
        raise ValueError("[Region]: Thiếu trường 'type'")
    
    kind = data["type"]
    if kind == "ROW":
        _require(data, kind, "number")
        return Row(int(data["number"]))
    if kind == "COLUMN":
        _require(data, kind, "letter")
        return Column(str(data["letter"]))
    if kind == "NEIGHBORS":
        _require(data, kind, "cell")
        return Neighbors(Cell.parse(data["cell"]))
    if kind == "CELLS":
        has_cells, has_profession = "cells" in data, "profession" in data
        if has_cells == has_profession:
            raise ValueError("[CELLS]: Cần đúng một trong hai trường 'cells' hoặc 'profession'")
        if has_profession:
            return ExplicitList(profession=data["profession"], plural=data.get("plural"))
        if "plural" in data:
            raise ValueError("[CELLS]: 'plural' chỉ dùng cùng 'profession'")
        return ExplicitList(tuple(Cell.parse(s) for s in data["cells"]))
    raise ValueError(f"[Region]: Loại vùng không hợp lệ: {kind!r}")
