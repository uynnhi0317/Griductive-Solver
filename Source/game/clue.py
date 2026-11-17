from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from .board import Board
from .cell import Cell
from .character import Status
from .region import Column, Region, Row, region_from_dict
from .phrasing import (
    among,
    count_sentence,
    inline,
    one_of_k_sentence,
    parity_sentence,
    status_noun,
    status_phrase,
)


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

def _require_fields(kind: str, data: Mapping[str, Any], *fields: str) -> None:
    """Ném ValueError nếu dict thiếu một trong các trường bắt buộc"""
    for field in fields:
        if field not in data:
            raise ValueError(f"[{kind}]: Thiếu trường '{field}'")


def _status_from(kind: str, raw: Any) -> Status:
    """Đọc trạng thái từ chuỗi 'CRIMINAL' / 'INNOCENT'"""
    try:
        return Status(raw)
    except (ValueError, TypeError):
        raise ValueError(f"[{kind}]: Trạng thái không hợp lệ: {raw!r}") from None


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
        return f"{_name(board, self.cell)} is {status_phrase(self.status)}"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FactClue":
        _require_fields(cls.kind, data, "cell", "status")
        return cls(Cell.parse(data["cell"]), _status_from(cls.kind, data["status"]))


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
        return count_sentence(self.region, board, self.kind, self.k)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "_CountClue":
        _require_fields(cls.kind, data, "k", "region")
        return cls(region_from_dict(data["region"]), data["k"])


@register_clue
@dataclass(frozen=True)
class ExactlyClue(_CountClue):
    """Đúng k tội phạm trong vùng"""
    kind: ClassVar[str] = "EXACTLY"


@register_clue
@dataclass(frozen=True)
class AtLeastClue(_CountClue):
    """Ít nhất k tội phạm trong vùng"""
    kind: ClassVar[str] = "AT_LEAST"


@register_clue
@dataclass(frozen=True)
class AtMostClue(_CountClue):
    """Nhiều nhất k tội phạm trong vùng"""
    kind: ClassVar[str] = "AT_MOST"

# ============================================================================
# Clue extensions: Clue mở rộng
# ============================================================================

_PARITIES = ("ODD", "EVEN")


def _is_adjacent(a: Cell, b: Cell) -> bool:
    """Kiểm tra hai ô kề nhau theo 8 hướng"""
    return a != b and max(abs(a.row - b.row), abs(a.col - b.col)) == 1


def adjacent_pairs(cells: tuple[Cell, ...]) -> tuple[tuple[Cell, Cell], ...]:
    """Các cặp ô kề nhau trong một tập ô, theo thứ tự xác định"""
    ordered = sorted(cells)
    return tuple(
        (a, b) for i, a in enumerate(ordered) for b in ordered[i + 1:] if _is_adjacent(a, b)
    )


def _optional_status(kind: str, data: Mapping[str, Any]) -> Status:
    """Trường status tuỳ chọn"""
    return _status_from(kind, data.get("status", Status.CRIMINAL.value))


@dataclass(frozen=True)
class _RegionStatusClue(Clue):
    """
    Cơ sở chung cho clue mở rộng nói về những người có trạng thái status trong một vùng.
    """
    region: Region
    status: Status = field(default=Status.CRIMINAL, kw_only=True)

    def _check_region_status(self) -> None:
        if not isinstance(self.region, Region):
            raise ValueError(f"[{self.kind}]: region không hợp lệ, nhận được {self.region!r}")
        if not isinstance(self.status, Status):
            raise ValueError(f"[{self.kind}]: Trạng thái không hợp lệ: {self.status!r}")

    def referenced_cells(self, board: Board) -> tuple[Cell, ...]:
        return self.region.cells(board)

    def _to_dict(self, **fields: Any) -> dict[str, Any]:
        return {"type": self.kind, "status": self.status.value, **fields, "region": self.region.to_dict()}

    @property
    def _plural(self) -> str:
        """Viết danh từ số nhiều"""
        return status_noun(self.status, 2)


@register_clue
@dataclass(frozen=True)
class ParityClue(_RegionStatusClue):
    """Số người có trạng thái status trong vùng là lẻ (ODD) hoặc chẵn (EVEN)"""
    kind: ClassVar[str] = "PARITY"
    parity: str

    def __post_init__(self) -> None:
        self._check_region_status()
        if self.parity not in _PARITIES:
            raise ValueError(f"[{self.kind}]: parity phải là ODD hoặc EVEN, nhận được {self.parity!r}")

    def validate(self, board: Board) -> None:
        cells = self.region.cells(board)
        if self.parity == "ODD" and not cells:
            raise ValueError(f"[{self.kind}]: Vùng rỗng không thể có số lẻ người")

    def to_dict(self) -> dict[str, Any]:
        return self._to_dict(parity=self.parity)

    def describe(self, board: Board) -> str:
        return parity_sentence(self.region, board, self.parity == "ODD", self.status)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ParityClue":
        _require_fields(cls.kind, data, "parity", "region")
        return cls(region_from_dict(data["region"]), data["parity"], status=_optional_status(cls.kind, data))


@register_clue
@dataclass(frozen=True)
class ConnectedClue(_RegionStatusClue):
    """
    Những người có trạng thái status trên một hàng/cột nằm liền nhau.
    """
    kind: ClassVar[str] = "CONNECTED"

    def __post_init__(self) -> None:
        self._check_region_status()
        if not isinstance(self.region, (Row, Column)):
            raise ValueError(f"[{self.kind}]: Chỉ áp dụng cho ROW hoặc COLUMN, nhận được {self.region!r}")

    def validate(self, board: Board) -> None:
        cells = self.region.cells(board)
        if len(cells) < 3:
            raise ValueError(f"[{self.kind}]: {self.region.describe()} chỉ có {len(cells)} ô, cần ít nhất 3 ô để clue có ý nghĩa")

    def to_dict(self) -> dict[str, Any]:
        return self._to_dict()

    def describe(self, board: Board) -> str:
        return f"All {self._plural} in {self.region.describe(board)} are connected"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConnectedClue":
        _require_fields(cls.kind, data, "region")
        return cls(region_from_dict(data["region"]), status=_optional_status(cls.kind, data))


@register_clue
@dataclass(frozen=True)
class NoAdjacentClue(_RegionStatusClue):
    """Không có hai người có trạng thái status nào trong vùng kề nhau (neighbors)"""
    kind: ClassVar[str] = "NO_ADJACENT"

    def __post_init__(self) -> None:
        self._check_region_status()

    def validate(self, board: Board) -> None:
        if not adjacent_pairs(self.region.cells(board)):
            raise ValueError(f"[{self.kind}]: {self.region.describe()} không có cặp ô kề nhau nào, clue vô nghĩa")

    def to_dict(self) -> dict[str, Any]:
        return self._to_dict()

    def describe(self, board: Board) -> str:
        return f"No two {self._plural} {among(self.region, board)} are next to each other"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NoAdjacentClue":
        _require_fields(cls.kind, data, "region")
        return cls(region_from_dict(data["region"]), status=_optional_status(cls.kind, data))


@register_clue
@dataclass(frozen=True)
class OneOfKClue(_RegionStatusClue):
    """
    Nhân vật tại ô cell là một trong đúng k người có trạng thái status trong vùng
    """
    kind: ClassVar[str] = "ONE_OF_K"
    cell: Cell
    k: int

    def __post_init__(self) -> None:
        self._check_region_status()
        if not isinstance(self.k, int):
            raise ValueError(f"[{self.kind}]: k phải là số nguyên, nhận được {self.k!r}")
        if self.k < 1:
            raise ValueError(f"[{self.kind}]: k phải >= 1, nhận được {self.k}")

    def validate(self, board: Board) -> None:
        _require_in_board(board, self.cell)
        cells = self.region.cells(board)
        if self.cell not in cells:
            raise ValueError(f"[{self.kind}]: Ô {self.cell.label} không thuộc {self.region.describe()}")
        if self.k > len(cells):
            raise ValueError(f"[{self.kind}]: k = {self.k} ngoài đoạn [1, {len(cells)}] của {self.region.describe()}")

    def to_dict(self) -> dict[str, Any]:
        return self._to_dict(cell=self.cell.label, k=self.k)

    def describe(self, board: Board) -> str:
        return one_of_k_sentence(_name(board, self.cell), self.region, board, self.k, self.status)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OneOfKClue":
        _require_fields(cls.kind, data, "cell", "k", "region")
        return cls(cell=Cell.parse(data["cell"]), region=region_from_dict(data["region"]), 
                   k=data["k"], status=_optional_status(cls.kind, data))


@register_clue
@dataclass(frozen=True)
class IfThenClue(Clue):
    """Nếu nhân vật tại cell có trạng thái status thì clue then_clue đúng"""
    kind: ClassVar[str] = "IF_THEN"
    cell: Cell
    status: Status
    then_clue: Clue

    def __post_init__(self) -> None:
        if not isinstance(self.status, Status):
            raise ValueError(f"[{self.kind}]: Trạng thái không hợp lệ: {self.status!r}")
        if not isinstance(self.then_clue, Clue):
            raise ValueError(f"[{self.kind}]: Vế sau phải là Clue, nhận được {self.then_clue!r}")

    def validate(self, board: Board) -> None:
        _require_in_board(board, self.cell)
        try:
            self.then_clue.validate(board)
        except ValueError as exc:
            raise ValueError(f"[{self.kind}]: Vế sau không hợp lệ: {exc}") from None

    def referenced_cells(self, board: Board) -> tuple[Cell, ...]:
        return tuple(sorted({self.cell, *self.then_clue.referenced_cells(board)}))

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind, "cell": self.cell.label, "status": self.status.value, "then": self.then_clue.to_dict()}

    def describe(self, board: Board) -> str:
        then_text = inline(self.then_clue.describe(board))
        return f"If {_name(board, self.cell)} is {status_phrase(self.status)}, {then_text}"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "IfThenClue":
        _require_fields(cls.kind, data, "cell", "status", "then")
        if not isinstance(data["then"], Mapping):
            raise ValueError(f"[{cls.kind}]: 'then' phải là một clue (object JSON)")
        return cls(Cell.parse(data["cell"]), _status_from(cls.kind, data["status"]), clue_from_dict(data["then"]))