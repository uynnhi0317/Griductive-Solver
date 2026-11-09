from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from .board import Board
from .cell import Cell
from .character import Status
from .region import Region, region_from_dict


class Clue(ABC):
    """Một manh mối có cấu trúc"""
    kind: ClassVar[str]

    @abstractmethod
    def validate(self, board: Board) -> None:
        """Ném ValueError nếu vùng tham chiếu không hợp lệ với board"""

    @abstractmethod
    def referenced_cells(self, board: Board) -> tuple[Cell, ...]:
        """Các ô được nhắc đến hoặc được đếm để GUI highlight"""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Chuyển clue thành dict để lưu vào JSON"""

    @abstractmethod
    def describe(self, board: Board) -> str:
        """Mô tả clue bằng ngôn ngữ tự nhiên để hiển thị"""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Clue":
        """Tạo clue từ dict"""



# Đăng ký loại clue vào bảng tra
_REGISTRY: dict[str, type[Clue]] = {}


def register_clue(cls):
    """Đăng ký loại clue theo cls.kind để clue_from_dict tìm được"""
    _REGISTRY[cls.kind] = cls
    return cls


def clue_from_dict(data: Mapping[str, Any]) -> Clue:
    """Tạo clue từ dict cho puzzle_loader"""
    try:
        kind = data["type"]
    except KeyError:
        raise ValueError("[Clue]: Thiếu trường 'type'") from None
    
    cls = _REGISTRY.get(kind)

    if cls is None:
        raise ValueError(f"[Clue]: Loại clue không hợp lệ: {kind!r}")
    
    return cls.from_dict(data)


def _require_in_board(board: Board, cell: Cell) -> None:
    if not board.contains(cell):
        raise ValueError(f"[Clue]: Ô {cell.label} ngoài board {board.size} x {board.size}")


def _name(board: Board, cell: Cell) -> str:
    """Trả về tên nhân vật tại một ô"""
    return board.character_at(cell).name


@register_clue
@dataclass(frozen=True)
class FactClue(Clue):
    """Một nhân vật có trạng thái cho trước"""
    kind: ClassVar[str] = "FACT"
    cell: Cell
    status: Status

    def __post_init__(self) -> None:
        if not isinstance(self.status, Status):
            raise ValueError(f"[FACT]: Trạng thái không hợp lệ: {self.status!r}")

    def validate(self, board: Board) -> None:
        _require_in_board(board, self.cell)

    def referenced_cells(self, board: Board) -> tuple[Cell, ...]:
        return (self.cell,)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "cell": self.cell.label, "status": self.status.value}

    def describe(self, board: Board) -> str:
        word = "a criminal" if self.status is Status.CRIMINAL else "innocent"
        return f"{_name(board, self.cell)} is {word}"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FactClue":
        for field in ("cell", "status"):
            if field not in data:
                raise ValueError(f"[FACT]: Thiếu trường '{field}'")

        status_raw = data["status"]
        try:
            status = Status[status_raw]
        except (KeyError, TypeError):
            raise ValueError(f"[FACT]: Trạng thái không hợp lệ: {status_raw!r}") from None

        return cls(Cell.parse(data["cell"]), status)


@dataclass(frozen=True)
class _PairClue(Clue):
    """Cơ sở chung cho clue về hai nhân vật khác nhau"""
    a: Cell
    b: Cell

    def __post_init__(self) -> None:
        if self.a == self.b:
            raise ValueError(f"[{self.kind}]: Hai nhân vật phải khác nhau, nhận được {self.a.label} hai lần")

    def validate(self, board: Board) -> None:
        _require_in_board(board, self.a)
        _require_in_board(board, self.b)

    def referenced_cells(self, board: Board) -> tuple[Cell, ...]:
        return tuple(sorted((self.a, self.b)))

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "cells": [self.a.label, self.b.label]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "_PairClue":
        cells = data.get("cells")
        if not isinstance(cells, (list, tuple)) or len(cells) != 2:
            raise ValueError(f"[{cls.kind}]: 'cells' phải gồm đúng 2 ô")
        
        return cls(Cell.parse(cells[0]), Cell.parse(cells[1]))

@register_clue
@dataclass(frozen=True)
class SameClue(_PairClue):
    """Hai nhân vật có cùng trạng thái"""
    kind: ClassVar[str] = "SAME"

    def describe(self, board: Board) -> str:
        return f"{_name(board, self.a)} and {_name(board, self.b)} are the same (both criminals or both innocents)"


@register_clue
@dataclass(frozen=True)
class DifferentClue(_PairClue):
    """Hai nhân vật có trạng thái khác nhau"""
    kind: ClassVar[str] = "DIFFERENT"

    def describe(self, board: Board) -> str:
        return f"{_name(board, self.a)} and {_name(board, self.b)} are different (one criminal, one innocent)"



@dataclass(frozen=True)
class _CountClue(Clue):
    """Cơ sở chung cho clue đếm số tội phạm trong một vùng"""
    region: Region
    k: int
    phrase: ClassVar[str]  # Từ ngữ biểu thị tương ứng với kind: Exactly/At least/At most

    def __post_init__(self) -> None:
        if not isinstance(self.k, int):
            raise ValueError(f"[{self.kind}]: k phải là số nguyên, nhận được {self.k!r}")
        if self.k < 0:
            raise ValueError(f"[{self.kind}]: k phải >= 0, nhận được {self.k}")
        if not isinstance(self.region, Region):
            raise ValueError(f"[{self.kind}]: region không hợp lệ, nhận được {self.region!r}")

    def validate(self, board: Board) -> None:
        cells = self.region.cells(board)  # tự ném ValueError nếu vùng sai
        if not 0 <= self.k <= len(cells):
            raise ValueError(f"[{self.kind}]: k = {self.k} ngoài đoạn [0, {len(cells)}] của {self.region.describe()}")

    def referenced_cells(self, board: Board) -> tuple[Cell, ...]:
        return self.region.cells(board)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "k": self.k, "region": self.region.to_dict()}

    def describe(self, board: Board) -> str:
        n = len(self.region.cells(board))
        return f"{self.phrase} {self.k} of the {n} cells in {self.region.describe()} are criminals"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "_CountClue":
        if "k" not in data:
            raise ValueError(f"[{cls.kind}]: Thiếu trường 'k'")

        if "region" not in data:
            raise ValueError(f"[{cls.kind}]: Thiếu trường 'region'")
        
        return cls(region_from_dict(data["region"]), data["k"])


@register_clue
@dataclass(frozen=True)
class ExactlyClue(_CountClue):
    """Đúng k tội phạm trong vùng"""
    kind: ClassVar[str] = "EXACTLY"
    phrase: ClassVar[str] = "Exactly"

    def describe(self, board: Board) -> str:
        if self.k == 0:
            return f"No criminals in {self.region.describe()}"
        return super().describe(board)


@register_clue
@dataclass(frozen=True)
class AtLeastClue(_CountClue):
    """Ít nhất k tội phạm trong vùng"""
    kind: ClassVar[str] = "AT_LEAST"
    phrase: ClassVar[str] = "At least"


@register_clue
@dataclass(frozen=True)
class AtMostClue(_CountClue):
    """Nhiều nhất k tội phạm trong vùng"""
    kind: ClassVar[str] = "AT_MOST"
    phrase: ClassVar[str] = "At most"
