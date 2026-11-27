import math
from dataclasses import dataclass

import pygame

from game.cell import Cell
from game.character import Character, Status
from .highlight import Role
from .theme import (
    Color, Face, Radius, Space, Size, Stroke, STATUS_COLOR, STAMP_COLOR, ROLE_COLOR,
    draw_rect_alpha, draw_status_icon, fit_line, fit_wrapped, get_font,
)

COMPACT_PX = 110        # thẻ nhỏ hơn ngưỡng này chỉ hiện huy hiệu + tên
SHAKE_DUR = 0.35
SHAKE_WAVES = 3
SHAKE_MIN_PX = 3
SHAKE_AMP_FRAC = 0.04
SELECT_SCALE = 1.03     # thẻ được chọn phóng to nhẹ
SELECT_ANIM = 0.12      # giây để phóng to / thu lại
ROLE_OUTSET = Space.xs
HINT_HZ = 1.2           # nhịp đập của vòng gợi ý
HINT_OUTSET = ROLE_OUTSET + Stroke.thick   # nằm ngoài vòng role, vẫn < Space.sm nên không đè thẻ kề
STAMP_ANGLE = 6         # độ, nghiêng ngược chiều kim đồng hồ
STAMP_ALPHA = 220


@dataclass(frozen=True)
class CardModel:
    cell: Cell
    character: Character
    status: Status | None      # None => face-down
    clue_text: str | None

    @property
    def face_up(self) -> bool:
        return self.status is not None


class CharacterCard:
    """
    Vẽ 1 card và animation của riêng nó.

    Quy tắc trạng thái (không bao giờ làm thẻ tối đi):
    + hover:    nền sáng lên (thẻ úp đổi sang card_back_hover, thẻ ngửa phủ lớp trắng mờ)
    + selected: vòng focus 3px + phóng to 1.03
    + role:     phủ màu mờ + viền màu, vẽ SAU vòng focus nên luôn nằm trên cùng
    """
    RADIUS = Radius.card

    def __init__(self, rect: pygame.Rect, model: CardModel):
        self.rect = rect
        self.flip_t = 1.0 if model.face_up else 0.0          # 0.0 = face-down, 1.0 = face-up
        self._target = self.flip_t
        self.sel_t = 0.0                                     # 0.0 = bình thường, 1.0 = đã phóng to
        self._shake_left = 0.0
        self._sel_target = False
        self.role: Role | None = None                        # vai trò highlight của clue đang chọn
        self.hint = False                                    # đang là mục tiêu của Hint
        self._hint_time = 0.0
        self._set_model(model)

    # ------------------------------------------------------ setting up
    def _set_model(self, model: CardModel) -> None:
        self.model = model
        self._back = self._render_back(Color.card_back)
        self._back_hover: pygame.Surface | None = None       # dựng lười khi hover lần đầu
        self._front = self._render_front() if model.face_up else None

    # ------------------------------------------------------ on change
    def sync(self, model: CardModel) -> None:
        if model == self.model:
            return
        self._set_model(model)
        self._target = 1.0 if model.face_up else 0.0   # start animating only on change
        if not self.model.face_up:
            self.flip_t = 0.0                          # snap on Restart/Load, no reverse animation

    def relayout(self, rect: pygame.Rect) -> None:
        """Gọi khi cửa sổ resize"""
        resized = rect.size != self.rect.size
        self.rect = rect
        if resized:
            self._set_model(self.model)    # re-render faces at the new size

    def shake(self) -> None:
        """Rung ngang khi verdict bị từ chối"""
        self._shake_left = SHAKE_DUR

    def _shake_offset(self) -> int:
        if self._shake_left <= 0:
            return 0
        t = 1.0 - self._shake_left / SHAKE_DUR
        amplitude = max(SHAKE_MIN_PX, self.rect.w * SHAKE_AMP_FRAC)
        return round(amplitude * math.sin(2 * math.pi * SHAKE_WAVES * t) * (1.0 - t))

    def update(self, dt: float, duration: float = 0.5) -> None:
        self._shake_left = max(0.0, self._shake_left - dt)
        step = dt / duration
        if self.flip_t < self._target:
            self.flip_t = min(self._target, self.flip_t + step)
        elif self.flip_t > self._target:
            self.flip_t = max(self._target, self.flip_t - step)

        sel_step = dt / SELECT_ANIM
        if self._sel_target:
            self.sel_t = min(1.0, self.sel_t + sel_step)
        else:
            self.sel_t = max(0.0, self.sel_t - sel_step)

        self._hint_time = self._hint_time + dt if self.hint else 0.0

    # ------------------------------------------------------ rendering
    def _blank(self, fill) -> pygame.Surface:
        w, h = self.rect.size
        face = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(face, fill, face.get_rect(), border_radius=self.RADIUS)
        return face

    def _render_stamp(self, w: int, h: int) -> pygame.Surface:
        """Con dấu CRIMINAL / INNOCENT: chữ máy đánh trong khung đôi, nghiêng nhẹ, hơi trong như mực"""
        status = self.model.status
        ink = STAMP_COLOR[status]
        font, text = fit_line(status.value, h // 9, int(w * 0.72) - 2 * Space.md,
                              bold=True, face=Face.TYPEWRITER)
        label = font.render(text, True, ink)
        stamp = pygame.Surface((label.get_width() + 2 * Space.md, label.get_height() + 2 * Space.xs),
                               pygame.SRCALPHA)
        rect = stamp.get_rect()
        pygame.draw.rect(stamp, ink, rect, width=Stroke.medium, border_radius=Radius.small)
        pygame.draw.rect(stamp, ink, rect.inflate(-3 * Stroke.medium, -3 * Stroke.medium),
                         width=Stroke.thin, border_radius=Radius.small)
        stamp.blit(label, label.get_rect(center=rect.center))
        stamp = pygame.transform.rotozoom(stamp, STAMP_ANGLE, 1.0)
        stamp.set_alpha(STAMP_ALPHA)
        return stamp

    def _render_back(self, fill) -> pygame.Surface:
        """Mặt úp: tên + nghề ở giữa, có viền sáng để tách khỏi nền"""
        w, h = self.rect.size
        face = self._blank(fill)
        pygame.draw.rect(face, Color.card_border, face.get_rect(), width=Stroke.thin, border_radius=self.RADIUS)
        self._blit_centered_name_job(face, w, h, Color.card_text, Color.card_text_dim)
        return face

    def _blit_centered_name_job(self, face: pygame.Surface, w: int, h: int,
                                ink=Color.card_text, ink_dim=Color.card_text_dim) -> None:
        ch = self.model.character
        max_w = w - 2 * Space.md
        font, text = fit_line(ch.name, h // 5, max_w, bold=True, face=Face.DISPLAY)
        name = font.render(text, True, ink)
        font, text = fit_line(ch.profession, h // 7, max_w)
        job = font.render(text, True, ink_dim)
        face.blit(name, name.get_rect(center=(w // 2, h * 2 // 5)))
        face.blit(job, job.get_rect(center=(w // 2, h * 3 // 5)))

    def _render_front(self) -> pygame.Surface:
        """Mặt ngửa: giấy da, viền màu trạng thái, huy hiệu ở góc, tên + nghề, clue, con dấu"""
        m = self.model
        w, h = self.rect.size
        face = self._blank(Color.card_face)
        pygame.draw.rect(face, STATUS_COLOR[m.status], face.get_rect(), width=Stroke.thick,
                         border_radius=self.RADIUS)

        badge_r = max(8, h // 14)
        draw_status_icon(face, m.status, w - Space.md - badge_r, Space.md + badge_r, badge_r)

        if min(w, h) < COMPACT_PX:
            font, text = fit_line(m.character.name, h // 4, w - 2 * Space.md, bold=True, face=Face.DISPLAY)
            txt = font.render(text, True, Color.card_text)
            face.blit(txt, txt.get_rect(center=(w // 2, h // 2)))
            return face

        if m.clue_text is None:
            self._blit_centered_name_job(face, w, h)
        else:
            self._blit_header(face, w, h, badge_r)
            area = pygame.Rect(Space.sm, h * 22 // 100, w - 2 * Space.sm, h * 54 // 100)
            font, lines = fit_wrapped(m.clue_text, area.w, area.h, max(10, h // 10))
            y = area.y + (area.h - len(lines) * font.get_linesize()) // 2
            face.set_clip(area)
            for line in lines:
                txt = font.render(line, True, Color.card_text)
                face.blit(txt, txt.get_rect(midtop=(w // 2, max(area.y, y))))
                y += font.get_linesize()
            face.set_clip(None)

        stamp = self._render_stamp(w, h)
        face.blit(stamp, stamp.get_rect(center=(w // 2, h * 88 // 100)))
        return face

    def _blit_header(self, face: pygame.Surface, w: int, h: int, badge_r: int) -> None:
        """
        Tên (đậm) và nghề trên MỘT dòng, chừa chỗ đối xứng cho huy hiệu để chữ vẫn canh giữa.
        Không vừa ở cỡ caption thì không in nghề, tên tự to lại (cắt '...' nếu vẫn dài).
        """
        ch = self.model.character
        margin = 2 * badge_r + Space.md + Space.sm
        max_w = w - 2 * margin
        gap = Space.sm
        start = max(Size.caption, h // 11)
        size = start
        can_show_job = True
        while True:
            name_font, job_font = get_font(size, True, Face.DISPLAY), get_font(size)
            total = name_font.size(ch.name)[0] + gap + job_font.size(ch.profession)[0]
            if total <= max_w:
                break
            if size > Size.caption:
                size -= 1
            else:
                can_show_job = False
                break

        cy = Space.md + badge_r
        if not can_show_job:
            name_font, text = fit_line(ch.name, start, max_w, bold=True, face=Face.DISPLAY)   # bỏ nghề thì tên to lại            name = name_font.render(text, True, Color.text)
            name = name_font.render(text, True, Color.card_text)
            return
        
        name = name_font.render(ch.name, True, Color.card_text)
        job = job_font.render(ch.profession, True, Color.card_text_dim)
        x = (w - (name.get_width() + gap + job.get_width())) // 2
        cy = Space.md + badge_r                       # cùng hàng với huy hiệu
        face.blit(name, name.get_rect(midleft=(x, cy)))
        face.blit(job, job.get_rect(midleft=(x + name.get_width() + gap, cy)))

    # ------------------------------------------------------ drawing
    def _showing_front(self) -> bool:
        return self.flip_t >= 0.5 and self._front is not None

    def _back_for(self, brighten: bool) -> pygame.Surface:
        if not brighten:
            return self._back
        if self._back_hover is None:
            self._back_hover = self._render_back(Color.card_back_hover)
        return self._back_hover

    def draw(self, surface, selected=False, hovered=False):
        self._sel_target = selected
        front = self._showing_front()
        face = self._front if front else self._back_for(hovered or selected)

        t = self.sel_t * self.sel_t * (3 - 2 * self.sel_t)       # smoothstep
        scale = 1.0 + (SELECT_SCALE - 1.0) * t
        w = max(1, int(self.rect.w * abs(math.cos(math.pi * self.flip_t)) * scale))
        h = max(1, int(self.rect.h * scale))
        img = face if (w, h) == face.get_size() else pygame.transform.smoothscale(face, (w, h))
        r = img.get_rect(center=(self.rect.centerx + self._shake_offset(), self.rect.centery))
        surface.blit(img, r)

        if hovered and front:
            draw_rect_alpha(surface, Color.hover_overlay, r, self.RADIUS)

        if selected:
            ring_w = min(Stroke.thick, max(1, w // 2))
            pygame.draw.rect(surface, Color.focus_edge, r, width=ring_w, border_radius=self.RADIUS)
            inner = r.inflate(-2 * ring_w, -2 * ring_w)
            if inner.w > 4 and inner.h > 4:
                pygame.draw.rect(surface, Color.focus, inner, width=Stroke.medium,
                                 border_radius=max(0, self.RADIUS - ring_w))

        if self.role is not None:
            color = ROLE_COLOR[self.role]
            if not front:     # thẻ ngửa giữ màu trạng thái, chỉ vẽ viền
                draw_rect_alpha(surface, (*color[:3], Color.role_tint), r, self.RADIUS)
            outer = r.inflate(2 * ROLE_OUTSET, 2 * ROLE_OUTSET)
            pygame.draw.rect(surface, color, outer, width=Stroke.thick,
                             border_radius=self.RADIUS + ROLE_OUTSET)

        if self.hint:
            pulse = 0.5 - 0.5 * math.cos(2 * math.pi * HINT_HZ * self._hint_time)
            draw_rect_alpha(surface, (*Color.hint[:3], int(25 + 60 * pulse)), r, self.RADIUS)
            ring = r.inflate(2 * HINT_OUTSET, 2 * HINT_OUTSET)
            shape = pygame.Surface(ring.size, pygame.SRCALPHA)
            pygame.draw.rect(shape, (*Color.hint[:3], int(110 + 145 * pulse)), shape.get_rect(),
                             width=Stroke.thick, border_radius=self.RADIUS + HINT_OUTSET)
            surface.blit(shape, ring)