"""
Adapter: clue -> {cell: Role} để GUI biết tô ô nào bằng màu nào

Không import pygame, không import loại clue cụ thể nào nên extension mới 
chạy được mà không phải sửa file này.

Cách hoạt động (theo thứ tự ưu tiên):
1. Clue tự định nghĩa `highlight_layers(board) -> Mapping[Cell, Role]` -> dùng đúng cái đó.
   Đây là cửa dành cho clue phức tạp (vd. "2 trong 5 tội phạm quanh Karl nằm ở hàng 3"
   cần vùng đếm + vùng điều kiện + chủ thể tách riêng).
2. Mặc định: mọi ô của `referenced_cells(board)` là COUNTED, rồi nâng cấp theo quy ước tên trường:
   - `cell`, `a`, `b` (kiểu Cell)      -> SUBJECT   (FACT, SAME, DIFFERENT, ONE_OF_K)
   - `region.center` (vùng NEIGHBORS)  -> SUBJECT   (ô trung tâm không nằm trong vùng neighbors)
   - `then_clue` (clue lồng nhau)      -> IF_THEN:  cell là CONDITION (vế "nếu"), vế "thì" tô đệ 
                                          quy như clue thường
"""

from enum import Enum
from typing import Mapping

from game.board import Board
from game.cell import Cell
from game.clue import Clue


class Role(Enum):
    """Vai trò của một ô đối với clue đang chọn. value lớn hơn = ưu tiên cao hơn khi một ô có nhiều vai trò"""
    COUNTED = 1      # ô nằm trong vùng được đếm / nhắc tới
    CONDITION = 2    # ô nằm trong vùng điều kiện phụ (chỉ dùng qua highlight_layers)
    SUBJECT = 3      # chủ thể của clue (người được nhắc tên, tâm của neighbors)


def _add(roles: dict[Cell, Role], cell: Cell, role: Role) -> None:
    current = roles.get(cell)
    if current is None or role.value > current.value:
        roles[cell] = role


def _merge(dst: dict[Cell, Role], src: Mapping[Cell, Role]) -> None:
    for cell, role in src.items():
        _add(dst, cell, role)


def _subject_cells(clue: Clue) -> list[Cell]:
    found = [v for name in ("cell", "a", "b") if isinstance(v := getattr(clue, name, None), Cell)]
    center = getattr(getattr(clue, "region", None), "center", None)
    if isinstance(center, Cell):
        found.append(center)
    return found


def highlight_roles(clue: Clue, board: Board) -> dict[Cell, Role]:
    """Các ô cần highlight khi clue được chọn, kèm vai trò"""
    custom = getattr(clue, "highlight_layers", None)
    if callable(custom):
        roles: dict[Cell, Role] = {}
        _merge(roles, custom(board))
        return roles

    roles = {}
    for cell in clue.referenced_cells(board):
        _add(roles, cell, Role.COUNTED)
    for cell in _subject_cells(clue):
        _add(roles, cell, Role.SUBJECT)

    nested = getattr(clue, "then_clue", None)
    if isinstance(nested, Clue):
        roles = {}
        _add(roles, clue.cell, Role.CONDITION)             # vế "nếu"
        _merge(roles, highlight_roles(nested, board))      # vế "thì"
    return roles