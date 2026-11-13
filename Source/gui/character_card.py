import pygame
import math
from dataclasses import dataclass
from game.character import Character, Status
from game.cell import Cell
from .theme import PALETTE, fit_font, get_font, draw_rect_alpha, STATUS_COLOR, SELECT_COLOR

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
        self._set_model(model)

    #______________________________________________________setting up
    def _set_model(self, model: CardModel) -> None:
        self.model = model
        self._front = self._render_face(STATUS_COLOR[model.status]) if model.face_up else None
        self._back = self._render_face(PALETTE["card_back"])

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
    def _convert_Status_str(self) -> str | None:
        if (not self.model.face_up): return None
        return "an innocent" if self.model.status == Status.INNOCENT else "a criminal"

    def _render_face(self, color) -> pygame.Surface:
        w, h = self.rect.size
        face = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(face, color, face.get_rect(), border_radius=self.RADIUS)

        char = self.model.character
        name = fit_font(char.name, h // 5, w - 12).render(char.name, True, PALETTE["text"])
        job = fit_font(char.profession, h//7, w - 12).render(char.profession, True, PALETTE["text"])
        if (self.model.face_up):
            s_str = self._convert_Status_str()
            status = fit_font(s_str, h//10, w - 12).render(f"is {s_str}", True, PALETTE["text"])
            face.blit(status, status.get_rect(center=(w // 2, h * 9 // 10)))
            
        face.blit(name, name.get_rect(center=(w // 2, h * 2 // 5)))
        face.blit(job, job.get_rect(center=(w // 2, h * 3 // 5)))
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

        if selected:
            key = SELECT_COLOR[self.model.status] if front else PALETTE["select_card_back"]
            pygame.draw.rect(surface, key, r, width=min(3, max(1, w // 2)), border_radius=self.RADIUS)
            draw_rect_alpha(surface, PALETTE["selected"], r, self.RADIUS)
        elif hovered:
            pygame.draw.rect(surface, PALETTE["hover"], r, width=min(2, max(1, w // 2)), border_radius=self.RADIUS)
            draw_rect_alpha(surface, PALETTE["hover"], r, self.RADIUS)
        