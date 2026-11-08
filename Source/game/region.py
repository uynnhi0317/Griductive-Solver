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
    def describe(self) -> str:
        """Mô tả của vùng để hiển thị"""


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

    def describe(self) -> str:
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

    def describe(self) -> str:
        return f"column {self.letter}"


@dataclass(frozen=True)
class Neighbors(Region):
    """Các ô kề của một ô"""
    center: Cell

    def cells(self, board: Board) -> tuple[Cell, ...]:
        return board.neighbor_cells(self.center)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "NEIGHBORS", "cell": self.center.label}

    def describe(self) -> str:
        return f"neighbors of {self.center.label}"


@dataclass(frozen=True)
class ExplicitList(Region):
    """Danh sách ô được liệt kê tường minh"""
    members: tuple[Cell, ...]

    def __post_init__(self) -> None:
        if not self.members:
            raise ValueError("[ExplicitList]: Vùng không được rỗng")
        if not all(isinstance(c, Cell) for c in self.members):
            raise ValueError("[ExplicitList]: Các phần tử phải là Cell")
        if len(set(self.members)) != len(self.members):
            raise ValueError("[ExplicitList]: Các ô trong vùng phải phân biệt")
        object.__setattr__(self, "members", tuple(sorted(self.members)))

    def cells(self, board: Board) -> tuple[Cell, ...]:
        for c in self.members:
            if not board.contains(c):
                raise ValueError(f"[ExplicitList]: Ô {c.label} ngoài board")
        return self.members

    def to_dict(self) -> dict[str, Any]:
        return {"type": "CELLS", "cells": [c.label for c in self.members]}

    def describe(self) -> str:
        return "cells " + ", ".join(c.label for c in self.members)


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
        _require(data, kind, "cells")
        return ExplicitList(tuple(Cell.parse(s) for s in data["cells"]))
    raise ValueError(f"[Region]: Loại vùng không hợp lệ: {kind!r}")
