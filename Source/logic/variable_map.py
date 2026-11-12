"""
Ánh xạ xác định hai chiều giữa nhân vật và biến

+ Biến chính C_i: 1..N*N theo row-major (A1 -> 1, B1 -> 2, ...), True = Criminal
+ Biến phụ: cấp bằng new_aux(), bắt đầu từ N*N + 1, tách riêng khỏi biến chính

VariableMap là nơi đặt ra quy ước biến.
"""

from typing import Mapping

from game.board import Board
from game.cell import Cell
from game.character import Status

def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)

class VariableMap:
    def __init__(self, board: Board) -> None:
        self._board = board
        self._num_main = board.size * board.size
        self._aux_tags: list[str | None] = []

    @property
    def board(self) -> Board:
        return self._board

    @property
    def num_main(self) -> int:
        """Số biến chính"""
        return self._num_main

    @property
    def num_aux(self) -> int:
        """Số biến phụ đã cấp"""
        return len(self._aux_tags)

    @property
    def max_var(self) -> int:
        """Số biến lớn nhất đã khai báo (gồm cả chính và phụ)"""
        return self._num_main + len(self._aux_tags)

    def var(self, cell: Cell) -> int:
        """Lấy biến của ô trong map"""
        return self._board.index_of(cell)

    def cell(self, var: int) -> Cell:
        """Lấy ô trong map khi có biến chính"""
        if not self.is_main(var):
            raise ValueError(f"[VariableMap]: {var!r} không phải biến chính (hợp lệ: 1..{self._num_main})")
        return self._board.cell_at(var)

    def literal(self, cell: Cell, criminal: bool = True) -> int:
        """Literal của ô: +C_i nếu criminal, -C_i nếu innocent"""
        if not isinstance(criminal, bool):
            raise ValueError(f"[VariableMap]: criminal phải là bool, nhận được {criminal!r}")
        v = self.var(cell)
        return v if criminal else -v

    def status_literal(self, cell: Cell, status: Status) -> int:
        """Literal biểu diễn một verdict đã chứng minh"""
        if not isinstance(status, Status):
            raise ValueError(f"[VariableMap]: Trạng thái không hợp lệ, nhận được {status!r}")
        return self.literal(cell, status is Status.CRIMINAL)

    def new_aux(self, tag: str | None = None) -> int:
        """Cấp một biến phụ mới, trả về số của biến mới"""
        self._aux_tags.append(tag)
        return self.max_var

    def aux_tag(self, var: int) -> str | None:
        """Nhãn của một biến phụ"""
        if not self.is_aux(var):
            raise ValueError(f"[VariableMap]: {var!r} không phải biến phụ đã cấp")
        return self._aux_tags[var - self._num_main - 1]

    def aux_vars(self) -> tuple[int, ...]:
        """Các biến phụ đã cấp, tăng dần"""
        return tuple(range(self._num_main + 1, self.max_var + 1))

    def is_main(self, var: int) -> bool:
        return _is_int(var) and 1 <= var <= self._num_main

    def is_aux(self, var: int) -> bool:
        return _is_int(var) and self._num_main < var <= self.max_var

    def decode(self, model: Mapping[int, bool]) -> dict[Cell, Status]:
        """
        Giải mã một model (biến -> bool) thành trạng thái từng nhân vật
        """
        statuses: dict[Cell, Status] = {}
        missing: list[int] = []

        # Chỉ ghi nhận giá trị các biến chính, không quan tâm biến phụ
        for cell in self._board.cells():
            v = self.var(cell)
            if v not in model:
                missing.append(v)
                continue
            value = model[v]
            if not isinstance(value, bool):
                raise ValueError(f"[VariableMap]: Giá trị của biến {v} phải là bool, nhận được {value!r}")
            statuses[cell] = Status.CRIMINAL if value else Status.INNOCENT

        # Một model phải trả về giá trị của tất cả biến chính    
        if missing:
            raise ValueError(f"[VariableMap]: Model thiếu biến chính: {missing}")
        
        return statuses
