"""
Hợp đồng chung của mọi thành phần GUI, để App chỉ định tuyến sự kiện và giữ layout
(không chứa hit-testing của ai):

+ fit(rect)           nhận vùng mới (lúc tạo và mỗi lần resize)
+ handle_event(e)     trả True nếu đã nuốt sự kiện; MOUSEMOTION nên trả False để mọi thành phần thấy hover
+ update(dt)          animation / đếm giờ, mặc định không làm gì
+ draw(surface)
"""

import pygame


class Component:
    def fit(self, rect: pygame.Rect) -> None:
        raise NotImplementedError

    def handle_event(self, e: pygame.event.Event) -> bool:
        return False

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        raise NotImplementedError