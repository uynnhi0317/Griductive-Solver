"""
Toàn bộ vị trí vùng của màn hình tính ở MỘT chỗ. Component chỉ nhận Rect từ đây,
nên resize chỉ cần gọi lại compute_layout() rồi fit() từng component.

+----------------------------------------------------------+
| top_bar                                                  |
+--------------------------------------+-------------------+
|                                      |                   |
|  board (thẻ được căn giữa, giới hạn  |  sidebar          |
|  cỡ thẻ trong BoardView)             |                   |
|                                      |                   |
+--------------------------------------+                   |
|  action_bar                          |                   |
+--------------------------------------+-------------------+
| status                                                   |
+----------------------------------------------------------+
"""

from dataclasses import dataclass

import pygame

from .theme import Space

MIN_WINDOW = (1024, 680)     # nhỏ hơn thì thẻ 3x3 chuyển sang dạng compact; vẫn vừa màn 1366x768
TOP_BAR_H = 44
STATUS_H = 50
ACTION_H = 52
SIDEBAR_FRAC = 0.30
SIDEBAR_MIN_W = 300


@dataclass(frozen=True)
class Layout:
    top_bar: pygame.Rect
    board: pygame.Rect
    action_bar: pygame.Rect
    sidebar: pygame.Rect
    status: pygame.Rect


def compute_layout(size: tuple[int, int]) -> Layout:
    w, h = size
    m = Space.lg
    sidebar_w = min(max(SIDEBAR_MIN_W, int(w * SIDEBAR_FRAC)), w // 2)
    middle_h = h - TOP_BAR_H - STATUS_H
    left_w = w - sidebar_w - 2 * m

    return Layout(
        top_bar=pygame.Rect(0, 0, w, TOP_BAR_H),
        board=pygame.Rect(0, TOP_BAR_H, left_w, middle_h - ACTION_H),
        action_bar=pygame.Rect(m, TOP_BAR_H + middle_h - ACTION_H, left_w - m, ACTION_H),
        sidebar=pygame.Rect(w - sidebar_w - m, TOP_BAR_H + m, sidebar_w, middle_h - 2 * m),
        status=pygame.Rect(0, h - STATUS_H, w, STATUS_H),
    )