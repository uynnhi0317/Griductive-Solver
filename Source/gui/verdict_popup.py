"""
Hộp thoại phán quyết, hiện giữa màn hình như bản Griductive gốc

+ VerdictDialog: bấm vào thẻ úp -> avatar, tên, ô · nghề, câu hỏi, 2 nút Innocent / Criminal và Cancel
+ ResultDialog:  verdict bị engine từ chối -> biểu tượng, tiêu đề, giải thích (in đậm tên / trạng thái), 1 nút quay lại
+ Cả hai là Overlay: App giữ tối đa một overlay, overlay nuốt mọi sự kiện nên không bấm nhầm xuống bàn cờ
+ Phím tắt: I / C chọn, Enter / Esc đóng; bấm ra ngoài khung = Cancel
"""
import functools
import math
from dataclasses import dataclass
from typing import Callable

import pygame

from engine.game_engine import VerdictOutcome
from game.character import Status
from .avatar import get_avatar
from .overlays import Overlay
from .theme import Color, Face, Radius, Size, Space, draw_rect_alpha, get_font, render_text

PANEL_W = 460
PANEL_PAD = Space.xl
BORDER_W = 3                  # viền đậm + bóng lệch: cùng phong cách khung của bản gốc
SHADOW_OFFSET = 8
AVATAR_PX = 84
AVATAR_ZOOM = 1.0             # avatar lấp đầy khung, phần lòi ra (vành nón, vai áo) bị cắt theo vòng tròn
AVATAR_DROP = 0.06            # đẩy avatar xuống một chút để vai áo chạm đáy khung tròn
ICON_R = 26
BIG_BTN_H = 56
LINK_H = 32
BTN_PRESS = 3                 # nút lún xuống khi nhấn (bóng lệch thu lại)

_INK = Color.text


def _mix(a: tuple, b: tuple, t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a[:3], b[:3]))


_WHITE = (255, 255, 255)


# ------------------------------------------------------------------ chữ có in đậm
def _rich_lines(text: str, size: int, max_w: int) -> list[list[tuple[str, bool, bool]]]:
    """
    Ngắt dòng văn bản có đánh dấu **đậm**. Mỗi dòng là các (mẩu chữ, đậm?, dính liền mẩu trước?).
    Tách theo dấu cách trước, rồi mới tách '**' trong từng từ: '**Bea**,' -> 'Bea' (đậm) + ',' (dính liền).
    """
    fonts = {False: get_font(size), True: get_font(size, True)}
    space_w = fonts[False].size(" ")[0]
    lines: list[list[tuple[str, bool, bool]]] = [[]]
    width, bold = 0, False
    for raw in text.split(" "):
        pieces, first = [], True
        for k, piece in enumerate(raw.split("**")):
            if k > 0:
                bold = not bold
            if piece:
                pieces.append((piece, bold, not first))
                first = False
        if not pieces:
            continue
        word_w = sum(fonts[b].size(t)[0] for t, b, _ in pieces)
        if lines[-1] and width + space_w + word_w > max_w:
            lines.append([])
            width = 0
        width += word_w + (space_w if lines[-1] else 0)
        lines[-1].extend(pieces)
    return [line for line in lines if line]


def _draw_rich(surface: pygame.Surface, text: str, size: int, color, center_x: int, y: int, max_w: int) -> int:
    """Vẽ văn bản **đậm** canh giữa từng dòng (phần đậm dùng màu mực đậm), trả về y sau dòng cuối"""
    fonts = {False: get_font(size), True: get_font(size, True)}
    space_w = fonts[False].size(" ")[0]
    line_h = int(fonts[False].get_linesize() * 1.15)
    for line in _rich_lines(text, size, max_w):
        gaps = [0 if k == 0 or glued else space_w for k, (_, _, glued) in enumerate(line)]
        total = sum(fonts[b].size(t)[0] for t, b, _ in line) + sum(gaps)
        x = center_x - total // 2
        for (piece, bold, _), gap in zip(line, gaps):
            x += gap
            img = render_text(piece, size, _INK if bold else color, bold)
            surface.blit(img, (x, y))
            x += img.get_width()
        y += line_h
    return y


# ------------------------------------------------------------------ avatar tròn
@functools.lru_cache(maxsize=64)
def _round_avatar(name: str, profession: str, d: int) -> pygame.Surface:
    """
    Avatar cắt theo hình tròn đường kính d: nền giấy, avatar phóng to + đẩy xuống để vai áo chạm đáy,
    rồi nhân với mặt nạ tròn (BLEND_RGBA_MIN) để mọi phần lòi ra ngoài (vành nón, vai áo) bị cắt bỏ.
    Mọi nhân vật vì vậy đều lấp đầy khung giống nhau.
    """
    canvas = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.circle(canvas, Color.surface_2, (d // 2, d // 2), d // 2)
    size = round(d * AVATAR_ZOOM)
    avatar = get_avatar(name, profession, size)
    if avatar is not None:
        canvas.blit(avatar, avatar.get_rect(midtop=(d // 2, round(d * AVATAR_DROP))))
    mask = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (d // 2, d // 2), d // 2)
    canvas.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return canvas


# ------------------------------------------------------------------ nút
@dataclass
class _DialogButton:
    """Nút lớn kiểu bản gốc: nền nhạt, viền + chữ đậm cùng màu, bóng lệch phía dưới"""
    label: str
    on_click: Callable[[], None]
    fill: tuple
    ink: tuple
    link: bool = False             # True: chỉ là chữ (Cancel), không có khung
    rect: pygame.Rect = None
    hovered: bool = False
    pressed: bool = False

    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(e.pos)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            self.pressed = True
            return True
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.pressed:
            self.pressed = False
            if self.rect.collidepoint(e.pos):
                self.on_click()
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if self.link:
            color = _INK if self.hovered else Color.text_dim
            img = render_text(self.label, Size.body, color, True)
            surface.blit(img, img.get_rect(center=self.rect.center))
            return
        drop = 0 if self.pressed else BTN_PRESS
        body = self.rect.move(0, BTN_PRESS - drop)
        shadow = body.move(0, drop) if drop else body
        pygame.draw.rect(surface, self.ink, shadow, border_radius=Radius.control + 2)
        fill = _mix(self.fill, _WHITE, 0.35) if self.hovered and not self.pressed else self.fill
        pygame.draw.rect(surface, fill, body, border_radius=Radius.control + 2)
        pygame.draw.rect(surface, self.ink, body, width=BORDER_W, border_radius=Radius.control + 2)
        img = render_text(self.label, Size.h2, self.ink, True)
        surface.blit(img, img.get_rect(center=body.center))


def _draw_card(surface: pygame.Surface, scrim_rect: pygame.Rect, panel: pygame.Rect) -> None:
    """Nền mờ + khung giấy viền đậm, bóng đặc lệch xuống phải"""
    draw_rect_alpha(surface, Color.scrim, scrim_rect)
    pygame.draw.rect(surface, _INK, panel.move(SHADOW_OFFSET, SHADOW_OFFSET), border_radius=Radius.card + 6)
    pygame.draw.rect(surface, Color.surface_1, panel, border_radius=Radius.card + 6)
    pygame.draw.rect(surface, _INK, panel, width=BORDER_W, border_radius=Radius.card + 6)


class _Dialog(Overlay):
    """Phần chung: tính chiều cao theo nội dung, bấm ngoài khung / Esc thì gọi on_dismiss"""

    def __init__(self, on_dismiss: Callable[[], None]) -> None:
        super().__init__()
        self._on_dismiss = on_dismiss
        self._buttons: list[_DialogButton] = []

    def _content_height(self, inner_w: int) -> int:
        raise NotImplementedError

    def _layout(self) -> None:
        pw = min(PANEL_W, self.rect.w - 2 * Space.xl)
        ph = self._content_height(pw - 2 * PANEL_PAD) + 2 * PANEL_PAD
        self.panel = pygame.Rect(0, 0, pw, ph)
        self.panel.center = self.rect.center
        self._place_buttons()

    def _place_buttons(self) -> None:
        raise NotImplementedError

    def handle_event(self, e: pygame.event.Event) -> bool:
        for b in self._buttons:
            if b.handle_event(e):
                return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and not self.panel.collidepoint(e.pos):
            self._on_dismiss()
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self._on_dismiss()
        return True


# ------------------------------------------------------------------ chọn verdict
VERDICT_QUESTION = "What's your verdict?"
VERDICT_BODY = ("Only a verdict the revealed clues can prove will be accepted. "
                "Get it right and the card turns over to reveal its clue.")


class VerdictDialog(_Dialog):
    def __init__(self, on_verdict: Callable[[Status], None], on_cancel: Callable[[], None]) -> None:
        super().__init__(on_cancel)
        self._on_verdict = on_verdict
        self.innocent = _DialogButton("Innocent", lambda: on_verdict(Status.INNOCENT),
                                      Color.card_face_innocent, Color.innocent)
        self.criminal = _DialogButton("Criminal", lambda: on_verdict(Status.CRIMINAL),
                                      Color.card_face_criminal, Color.criminal)
        self.cancel = _DialogButton("Cancel", on_cancel, Color.surface_1, Color.text_dim, link=True)
        self._buttons = [self.innocent, self.criminal, self.cancel]
        self.name = self.profession = self.cell_label = ""

    def open(self, name: str, profession: str, cell_label: str) -> None:
        self.name, self.profession, self.cell_label = name, profession, cell_label
        for b in self._buttons:
            b.hovered = b.pressed = False
        self._layout()

    def _content_height(self, inner_w: int) -> int:
        body_lines = len(_rich_lines(VERDICT_BODY, Size.body, inner_w))
        return (AVATAR_PX + Space.sm + get_font(Size.h2, True, Face.DISPLAY).get_linesize()
                + get_font(Size.caption, face=Face.TYPEWRITER).get_linesize() + Space.lg
                + get_font(Size.h2, face=Face.TYPEWRITER).get_linesize() + Space.sm
                + int(body_lines * get_font(Size.body).get_linesize() * 1.15) + Space.lg
                + BIG_BTN_H + Space.md + LINK_H)

    def _place_buttons(self) -> None:
        p = self.panel
        bottom = p.bottom - PANEL_PAD
        self.cancel.rect = pygame.Rect(p.centerx - 60, bottom - LINK_H, 120, LINK_H)
        half = (p.w - 2 * PANEL_PAD - Space.md) // 2
        y = self.cancel.rect.top - Space.md - BIG_BTN_H
        self.innocent.rect = pygame.Rect(p.x + PANEL_PAD, y, half, BIG_BTN_H - BTN_PRESS)
        self.criminal.rect = pygame.Rect(self.innocent.rect.right + Space.md, y, half, BIG_BTN_H - BTN_PRESS)

    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.KEYDOWN and e.key == pygame.K_i:
            self._on_verdict(Status.INNOCENT)
            return True
        if e.type == pygame.KEYDOWN and e.key == pygame.K_c:
            self._on_verdict(Status.CRIMINAL)
            return True
        return super().handle_event(e)

    def draw(self, surface: pygame.Surface) -> None:
        p = self.panel
        _draw_card(surface, self.rect, p)
        cx, y = p.centerx, p.y + PANEL_PAD

        ring = pygame.Rect(0, 0, AVATAR_PX, AVATAR_PX)
        ring.midtop = (cx, y)
        surface.blit(_round_avatar(self.name, self.profession, AVATAR_PX), ring)
        pygame.draw.circle(surface, _INK, ring.center, AVATAR_PX // 2, width=BORDER_W)
        y = ring.bottom + Space.sm

        name = render_text(self.name, Size.h2, _INK, True, Face.DISPLAY)
        surface.blit(name, name.get_rect(midtop=(cx, y)))
        y += get_font(Size.h2, True, Face.DISPLAY).get_linesize()
        sub = render_text(f"{self.cell_label} · {self.profession}", Size.caption, Color.text_dim, False, Face.TYPEWRITER)
        surface.blit(sub, sub.get_rect(midtop=(cx, y)))
        y += get_font(Size.caption, face=Face.TYPEWRITER).get_linesize() + Space.lg

        q = render_text(VERDICT_QUESTION, Size.h2, _INK, False, Face.TYPEWRITER)
        surface.blit(q, q.get_rect(midtop=(cx, y)))
        y += get_font(Size.h2, face=Face.TYPEWRITER).get_linesize() + Space.sm
        _draw_rich(surface, VERDICT_BODY, Size.body, Color.text_dim, cx, y, p.w - 2 * PANEL_PAD)

        for b in self._buttons:
            b.draw(surface)


# ------------------------------------------------------------------ kết quả bị từ chối
_RESULT_TEXT = {
    VerdictOutcome.NOT_PROVABLE: (
        "Not enough evidence yet",
        "The clues revealed so far don't prove that **{name}** is **{said}**. "
        "**{name}** could still be **{other}** without breaking a single clue. "
        "Reveal more clues first, or ask for a hint.",
    ),
    VerdictOutcome.CONTRADICTED: (
        "That contradicts the clues",
        "Calling **{name}** **{said}** breaks what the revealed clues already establish. "
        "Read the clues around **{name}** again before deciding.",
    ),
}
RESULT_BUTTON = "Back to the case"


class ResultDialog(_Dialog):
    def __init__(self, on_close: Callable[[], None]) -> None:
        super().__init__(on_close)
        self.back = _DialogButton(RESULT_BUTTON, on_close, _mix(Color.fb_error, _WHITE, 0.45), _INK)
        self._buttons = [self.back]
        self.outcome = VerdictOutcome.NOT_PROVABLE
        self.title = self.body = ""

    def open(self, outcome: VerdictOutcome, name: str, said: Status) -> None:
        other = Status.CRIMINAL if said is Status.INNOCENT else Status.INNOCENT
        self.outcome = outcome
        self.title, template = _RESULT_TEXT[outcome]
        self.body = template.format(name=name, said=said.value.lower(), other=other.value.lower())
        self.back.hovered = self.back.pressed = False
        self._layout()

    def _content_height(self, inner_w: int) -> int:
        body_lines = len(_rich_lines(self.body, Size.body, inner_w))
        return (2 * ICON_R + Space.md + get_font(Size.title, face=Face.TYPEWRITER).get_linesize() + Space.sm
                + int(body_lines * get_font(Size.body).get_linesize() * 1.15) + Space.lg + BIG_BTN_H)

    def _place_buttons(self) -> None:
        p = self.panel
        w = min(260, p.w - 2 * PANEL_PAD)
        self.back.rect = pygame.Rect(0, 0, w, BIG_BTN_H - BTN_PRESS)
        self.back.rect.midbottom = (p.centerx, p.bottom - PANEL_PAD - BTN_PRESS)

    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._on_dismiss()
            return True
        return super().handle_event(e)

    def _draw_icon(self, surface: pygame.Surface, center: tuple[int, int]) -> None:
        """Cảnh báo (tam giác !) cho NOT_PROVABLE, dấu X cho CONTRADICTED; vòng tròn nền nhạt viền đậm"""
        color = Color.fb_warn if self.outcome is VerdictOutcome.NOT_PROVABLE else Color.fb_error
        pygame.draw.circle(surface, _mix(color, _WHITE, 0.75), center, ICON_R)
        pygame.draw.circle(surface, color, center, ICON_R, width=BORDER_W)
        cx, cy = center
        if self.outcome is VerdictOutcome.NOT_PROVABLE:
            s = ICON_R * 0.66
            tri = [(cx, cy - s), (cx + s * math.sin(math.pi / 3), cy + s * 0.6),
                   (cx - s * math.sin(math.pi / 3), cy + s * 0.6)]
            pygame.draw.polygon(surface, color, tri, width=BORDER_W)
            pygame.draw.line(surface, color, (cx, cy - s * 0.38), (cx, cy + s * 0.12), BORDER_W)
            pygame.draw.circle(surface, color, (cx, round(cy + s * 0.37)), BORDER_W - 1)
        else:
            d = ICON_R * 0.38
            pygame.draw.line(surface, color, (cx - d, cy - d), (cx + d, cy + d), BORDER_W + 1)
            pygame.draw.line(surface, color, (cx - d, cy + d), (cx + d, cy - d), BORDER_W + 1)

    def draw(self, surface: pygame.Surface) -> None:
        p = self.panel
        _draw_card(surface, self.rect, p)
        cx, y = p.centerx, p.y + PANEL_PAD
        self._draw_icon(surface, (cx, y + ICON_R))
        y += 2 * ICON_R + Space.md
        t = render_text(self.title, Size.title, _INK, False, Face.TYPEWRITER)
        surface.blit(t, t.get_rect(midtop=(cx, y)))
        y += get_font(Size.title, face=Face.TYPEWRITER).get_linesize() + Space.sm
        _draw_rich(surface, self.body, Size.body, Color.text_dim, cx, y, p.w - 2 * PANEL_PAD)
        self.back.draw(surface)
