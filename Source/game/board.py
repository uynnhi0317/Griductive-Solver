from typing import Mapping

from .character import Character
from .cell import Cell

_NEIGHBOR_DELTAS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0)]

class Board:
    MAX_SIZE = 5

    def __init__(self, size: int, characters: Mapping[Cell, Character]) -> None:
        if not 1 <= size <= self.MAX_SIZE:
            raise ValueError(f"[Board]: Kích thước board phải nằm từ 1 đến {self.MAX_SIZE}], kích thước nhận được: {size}")
        
        self._size = size
        self._cells: tuple[Cell, ...] = tuple(
            Cell(r, c) for r in range(1, size + 1) for c in range(1, size + 1)
        )

        if set(characters) != set(self._cells):
            raise ValueError(f"[Board]: Board {size} x {size} cần đúng {size * size} nhân vật, mỗi nhân vật một ô")
        
        names = [ch.name for ch in characters.values()]
        if len(set(names)) != len(names):
            raise ValueError("[Board]: Tên nhân vật phải phân biệt")

        self._by_cell = dict(characters)
        self._cell_of_name = {ch.name: cell for cell, ch in self._by_cell.items()}

    @classmethod
    def from_dict(cls, size: int, data: Mapping[str, Mapping[str, str]]) -> "Board":
        """
        Đọc dữ liệu nhân vật từ mapping
        data = {"A1": {"name": "Abel", "profession": "Astronaut"}, ...}
        """
        chars = {Cell.parse(k): Character(v["name"], v["profession"]) for k, v in data.items()}
        return cls(size, chars)

    @property
    def size(self) -> int:
        return self._size

    def cells(self) -> tuple[Cell, ...]:
        """Lấy tất cả ô theo thứ tự row-major"""
        return self._cells

    def contains(self, cell: Cell) -> bool:
        """Kiểm tra ô có nằm trong board"""
        return 1 <= cell.row <= self._size and 1 <= cell.col <= self._size

    def character_at(self, cell: Cell) -> Character:
        """Truy vấn nhân vật tại ô"""
        self._require(cell)
        return self._by_cell[cell]

    def cell_of(self, name: str) -> Cell:
        """Lấy tọa độ ô từ tên"""
        try:
            return self._cell_of_name[name]
        except KeyError:
            raise KeyError(f"[Board] Nhân vật không có trên board: {name!r}") from None

    def index_of(self, cell: Cell) -> int:
        """Chỉ số row-major 1-based"""
        self._require(cell)
        return (cell.row - 1) * self._size + cell.col

    def cell_at(self, index: int) -> Cell:
        """Lấy tọa độ ô theo vị trí đánh số"""
        return self._cells[index - 1]

    def cells_by_name(self) -> tuple[Cell, ...]:
        """Các ô sắp theo tên nhân vật (alphabetical)"""
        return tuple(sorted(self._cells, key=lambda c: self._by_cell[c].name))

    def row_cells(self, row: int) -> tuple[Cell, ...]:
        """Lấy các ô trên 1 hàng"""
        if not 1 <= row <= self._size:
            raise ValueError(f"[Board] Chỉ số hàng ngoài phạm vi: {row}")
        return tuple(Cell(row, c) for c in range(1, self._size + 1))

    def column_cells(self, col: int) -> tuple[Cell, ...]:
        """Lấy các ô trên 1 dòng"""
        if not 1 <= col <= self._size:
            raise ValueError(f"[Board] Chỉ số cột ngoài phạm vi: {col}")
        return tuple(Cell(r, col) for r in range(1, self._size + 1))

    def neighbor_cells(self, cell: Cell) -> tuple[Cell, ...]:
        """Lấy các ô neighbor"""
        self._require(cell)
        result = [Cell(cell.row + dr, cell.col + dc) for dr, dc in _NEIGHBOR_DELTAS]
        return tuple(sorted(c for c in result if self.contains(c)))

    def _require(self, cell: Cell) -> None:
        if not self.contains(cell):
            raise ValueError(f"[Board] Ô {cell.label} ngoài board {self._size} x {self._size}")
        