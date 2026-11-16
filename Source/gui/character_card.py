import pygame
import math
from dataclasses import dataclass
from game.character import Character, Status
from game.cell import Cell
from .highlight import Role
from .theme import PALETTE, fit_font, get_font, draw_rect_alpha, STATUS_COLOR, SELECT_COLOR, ROLE_COLOR, fit_wrapped

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
    """Vẽ 1 card và animation của riêng nó"""
    RADIUS = 10

    def __init__(self, rect: pygame.Rect, model: CardModel):
        self.rect = rect
        self.flip_t = 1.0 if model.face_up else 0.0          # 0.0 = face-down, 1.0 = face-up
        self._target = self.flip_t
        self.role: Role | None = None                        # vai trò highlight của clue đang chọn
        self._set_model(model)

    #______________________________________________________setting up
    def _set_model(self, model: CardModel) -> None:
        self.model = model
        self._back = self._render_face(PALETTE["card_back"])
        self._front = (self._render_face(STATUS_COLOR[model.status], model.status.value, model.clue_text)
                    if model.face_up else None)
    #______________________________________________________on change
        
    def sync(self, model: CardModel) -> None:
        if model == self.model:
            return
        self._set_model(model)
        self._target = 1.0 if model.face_up else 0.0   # start animating only on change
        if (not self.model.face_up):
            self.flip_t = 0.0                          # snap on Restart/Load, no reverse animation

    def relayout(self, rect: pygame.Rect) -> None:
        """Gọi khi cửa sổ resize"""
        resized = rect.size != self.rect.size
        self.rect = rect
        if resized:
            self._set_model(self.model)    # re-render faces at the new size

    def update(self, dt: float, duration: float = 0.5) -> None: 
        step = dt / duration
        if self.flip_t < self._target:
            self.flip_t = min(self._target, self.flip_t + step)
        elif self.flip_t > self._target:
            self.flip_t = max(self._target, self.flip_t - step)

    #________________________________________________________________show
    def _render_face(self, color, status_text: str | None = None, clue_text: str | None = None) -> pygame.Surface:
        w, h = self.rect.size
        face = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(face, color, face.get_rect(), border_radius=self.RADIUS)

        ch = self.model.character
        if clue_text is None:
            # mặt úp (hoặc thẻ lật không có clue): tên + nghề ở giữa
            name = fit_font(ch.name, h // 5, w - 12).render(ch.name, True, PALETTE["text"])
            job = fit_font(ch.profession, h // 7, w - 12).render(ch.profession, True, PALETTE["text"])
            face.blit(name, name.get_rect(center=(w // 2, h * 2 // 5)))
            face.blit(job, job.get_rect(center=(w // 2, h * 3 // 5)))
        else:
            # mặt ngửa có clue: tên + nghề ở trên, clue ở giữa, trạng thái ở dưới
            name = fit_font(ch.name, h // 8, w - 12).render(ch.name, True, PALETTE["text"])
            job = fit_font(ch.profession, h // 12, w - 12).render(ch.profession, True, PALETTE["text"])
            face.blit(name, name.get_rect(center=(w // 2, h * 13 // 100)))
            face.blit(job, job.get_rect(center=(w // 2, h * 25 // 100)))

            area = pygame.Rect(8, h * 33 // 100, w - 16, h * 47 // 100)
            font, lines = fit_wrapped(clue_text, area.w, area.h, max(10, h // 10))
            y = area.y + (area.h - len(lines) * font.get_linesize()) // 2   # canh giữa theo chiều dọc
            face.set_clip(area)
            for line in lines:
                txt = font.render(line, True, PALETTE["text"])
                face.blit(txt, txt.get_rect(midtop=(w // 2, max(area.y, y))))
                y += font.get_linesize()
            face.set_clip(None)

        if status_text:
            label = f"is {status_text}"
            txt = fit_font(label, h // 11, w - 12).render(label, True, PALETTE["text"])
            face.blit(txt, txt.get_rect(center=(w // 2, h * 91 // 100)))
        return face

    def _showing_front(self) -> bool:
        return self.flip_t >= 0.5 and self._front is not None

    def draw(self, surface, selected=False, hovered=False):
        front = self._showing_front()
        face = self._front if front else self._back
        w = max(1, int(self.rect.w * abs(math.cos(math.pi * self.flip_t))))
        img = face if w == self.rect.w else pygame.transform.smoothscale(face, (w, self.rect.h))
        r = img.get_rect(center=self.rect.center)
        surface.blit(img, r)

        # Chỉ một kiểu highlight cho mỗi thẻ, ưu tiên: role (clue đang chọn) > selected > hover
        if self.role is not None:
            color = ROLE_COLOR[self.role]
            pygame.draw.rect(surface, color, r, width=min(4, max(1, w // 2)), border_radius=self.RADIUS)
        elif selected:
            key = SELECT_COLOR[self.model.status] if front else PALETTE["select_card_back"]
            pygame.draw.rect(surface, key, r, width=min(3, max(1, w // 2)), border_radius=self.RADIUS)
            draw_rect_alpha(surface, PALETTE["selected"], r, self.RADIUS)
        elif hovered:
            pygame.draw.rect(surface, PALETTE["hover"], r, width=min(2, max(1, w // 2)), border_radius=self.RADIUS)
            draw_rect_alpha(surface, PALETTE["hover"], r, self.RADIUS)