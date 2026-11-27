import math
from dataclasses import dataclass

import pygame

from game.cell import Cell
from game.character import Character, Status
from .avatar import get_avatar
from .highlight import Role
from .theme import (
    Color, Face, Radius, Space, Size, Stroke, FACE_COLOR, STATUS_COLOR, STAMP_COLOR, ROLE_COLOR,
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
AVATAR_W_FRAC = 0.55    # avatar ở giữa thẻ: tối đa 55% chiều rộng
AVATAR_H_FRAC = 0.46    # và 46% chiều cao, chừa chỗ cho tên + nghề bên dưới
AVATAR_BOTTOM = 0.56    # đáy avatar nằm ở 56% chiều cao thẻ
STAMP_TOP = 0.78        # mặt ngửa: con dấu chiếm phần dưới, avatar + chữ phải nằm trên mức này
AVATAR_MIN_PX = 64      # thẻ nhỏ hơn mức này (lưới 5x5 trên màn hình nhỏ) mới bỏ avatar, chỉ còn chữ


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
                                ink=Color.card_text, ink_dim=Color.card_text_dim,
                                bottom: float = 1.0) -> None:
        """
        Avatar + tên + nghề canh giữa. `bottom` (0..1] là phần chiều cao được dùng tính từ mép trên:
        mặt úp dùng cả thẻ (1.0), mặt ngửa chừa chỗ cho con dấu (STAMP_TOP)
        """
        ch = self.model.character
        max_w = w - 2 * Space.md
        room = h * bottom
        avatar = None
        if min(w, h) >= AVATAR_MIN_PX:  # thẻ quá nhỏ không đủ chỗ, giữ bố cục chữ như cũ
            avatar = self._avatar(min(int(w * AVATAR_W_FRAC), int(room * AVATAR_H_FRAC)))

        if avatar is None:
            name_px, job_px, name_y, job_y = h // 5, h // 7, h * 2 // 5, h * 3 // 5
        else:                           # avatar ở trên, tên + nghề dồn xuống dưới và nhỏ lại
            face.blit(avatar, avatar.get_rect(midbottom=(w // 2, int(room * AVATAR_BOTTOM))))
            name_px, job_px = int(room / 6), int(room / 9)
            name_y, job_y = int(room * 0.68), int(room * 0.82)

        font, text = fit_line(ch.name, name_px, max_w, bold=True, face=Face.DISPLAY)
        name = font.render(text, True, ink)
        font, text = fit_line(ch.profession, job_px, max_w)
        job = font.render(text, True, ink_dim)
        face.blit(name, name.get_rect(center=(w // 2, name_y)))
        face.blit(job, job.get_rect(center=(w // 2, job_y)))

    def _avatar(self, size: int) -> pygame.Surface | None:
        """Avatar vuông của nhân vật trên thẻ (đã cache theo tên + nghề + kích thước)"""
        ch = self.model.character
        return get_avatar(ch.name, ch.profession, size)

    def _render_front(self) -> pygame.Surface:
        """
        Mặt ngửa: giấy da, viền màu trạng thái, huy hiệu ở góc, tên + nghề, clue, con dấu.
        Thẻ nhỏ (< COMPACT_PX, vd. lưới 5x5): lề hẹp hơn, bỏ con dấu (viền + huy hiệu đã cho biết
        kết luận) để nhường chỗ cho clue; thẻ quá nhỏ (< AVATAR_MIN_PX) chỉ còn tên.
        """
        m = self.model
        w, h = self.rect.size
        compact = min(w, h) < COMPACT_PX
        inset = Space.sm if compact else Space.md     # khoảng cách từ mép thẻ tới huy hiệu / avatar góc
        face = self._blank(FACE_COLOR[m.status])     # nền ngả xanh / đỏ theo kết luận
        pygame.draw.rect(face, STATUS_COLOR[m.status], face.get_rect(), width=Stroke.thick,
                         border_radius=self.RADIUS)

        badge_r = max(8, h // 14)
        draw_status_icon(face, m.status, w - inset - badge_r, inset + badge_r, badge_r)

        if min(w, h) < AVATAR_MIN_PX:                 # quá nhỏ: chỉ đủ chỗ cho tên
            font, text = fit_line(m.character.name, h // 4, w - 2 * Space.sm, bold=True, face=Face.DISPLAY)
            txt = font.render(text, True, Color.card_text)
            face.blit(txt, txt.get_rect(center=(w // 2, h // 2)))
            return face

        if m.clue_text is None:
            self._blit_centered_name_job(face, w, h, bottom=1.0 if compact else STAMP_TOP)
        else:
            header_bottom = self._blit_header(face, w, h, badge_r, inset)
            top = header_bottom + Space.xs
            if compact:                               # không có con dấu: clue dùng hết phần dưới header
                area = pygame.Rect(Space.xs, top, w - 2 * Space.xs, h - top - Space.xs)
            else:                                     # chừa phần dưới cho con dấu
                area = pygame.Rect(Space.sm, top, w - 2 * Space.sm, h * 76 // 100 - top)
            font, lines = fit_wrapped(m.clue_text, area.w, area.h, max(10, h // 10))
            y = area.y + (area.h - len(lines) * font.get_linesize()) // 2
            face.set_clip(area)
            for line in lines:
                txt = font.render(line, True, Color.card_text)
                face.blit(txt, txt.get_rect(midtop=(w // 2, max(area.y, y))))
                y += font.get_linesize()
            face.set_clip(None)

        if not compact:
            stamp = self._render_stamp(w, h)
            face.blit(stamp, stamp.get_rect(center=(w // 2, h * 88 // 100)))
        return face

    def _blit_header(self, face: pygame.Surface, w: int, h: int, badge_r: int,
                     inset: int = Space.md) -> int:
        """
        Header giống bản gốc: [avatar | tên đậm / nghề bên dưới] gộp thành MỘT nhóm canh giữa thẻ;
        nhóm chỉ lùi sang trái khi sắp đè huy hiệu góc phải. Thẻ nhỏ chỉ có [avatar | tên] một dòng.
        Không vừa thì lần lượt: thu nhỏ chữ (tới cỡ caption) -> bỏ nghề -> bỏ avatar, cắt '...'.
        Trả về y của đáy header để clue bắt đầu ngay bên dưới.
        """
        ch = self.model.character
        compact = inset < Space.md
        right = w - inset - 2 * badge_r - (Space.xs if compact else Space.sm)   # mép phải trước huy hiệu
        max_w = right - inset
        gap = Space.xs if compact else Space.sm       # khoảng cách avatar -> chữ
        floor = Size.min_text if compact else Size.caption   # thẻ nhỏ cho tên nhỏ hơn để clue còn chỗ
        start = max(floor, h // 8) if compact else max(Size.caption, h // 11)

        for show_job in ((False,) if compact else (True, False)):
            for size in range(start, floor - 1, -1):
                name_font = get_font(size, True, Face.DISPLAY)
                job_font = get_font(max(Size.min_text, size - 3))
                text_w = name_font.size(ch.name)[0]
                text_h = name_font.get_ascent()      # bỏ phần đệm dưới của Oswald để 2 dòng sát nhau
                if show_job:
                    text_w = max(text_w, job_font.size(ch.profession)[0])
                    text_h += job_font.get_height()
                else:
                    text_h = name_font.get_height()
                av_size = max(2 * badge_r, text_h)
                if av_size + gap + text_w > max_w:
                    continue
                avatar = self._avatar(av_size)
                group_w = (av_size + gap if avatar is not None else 0) + text_w
                x = max(inset, min((w - group_w) // 2, right - group_w))   # giữa thẻ, lùi trái nếu chạm huy hiệu
                cy = inset + av_size // 2
                if avatar is not None:
                    face.blit(avatar, avatar.get_rect(midleft=(x, cy)))
                    x += av_size + gap
                y = cy - text_h // 2
                face.blit(name_font.render(ch.name, True, Color.card_text), (x, y))
                if show_job:
                    job = job_font.render(ch.profession, True, Color.card_text_dim)
                    face.blit(job, (x, y + name_font.get_ascent()))
                return inset + av_size

        # không nhóm nào vừa: chỉ còn tên canh giữa, cắt '...'
        name_font, text = fit_line(ch.name, start, max_w, bold=True, face=Face.DISPLAY)
        name = name_font.render(text, True, Color.card_text)
        face.blit(name, name.get_rect(center=(w // 2, inset + badge_r)))
        return inset + 2 * badge_r

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