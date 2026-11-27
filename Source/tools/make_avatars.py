"""
Xuất avatar PNG cho nhân vật trong các puzzle, dùng chung code vẽ với GUI (gui/avatar.py)

GUI tự sinh avatar lúc chạy nên KHÔNG bắt buộc chạy script này. Dùng khi muốn:
+ xem trước cả bộ nhân vật (preview.png) để chụp vào báo cáo
+ xuất PNG ra gui/assets/avatars/ rồi sửa tay một vài ảnh (GUI ưu tiên file PNG nếu có)

Chạy từ thư mục Source/:
  python tools/make_avatars.py                                   # mọi puzzle, chỉ tạo preview
  python tools/make_avatars.py puzzles/4x4/4x4_01.json --png     # xuất PNG ra gui/assets/avatars/
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOURCE_DIR))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # không mở cửa sổ

import pygame  # noqa: E402

from gui.avatar import AVATAR_DIR, get_avatar, guess_gender  # noqa: E402

PREVIEW_COLS = 8
LABEL_H = 34


def collect_characters(paths: list[str]) -> dict[str, str]:
    """{tên: nghề} từ trường "characters" của các file puzzle; tên trùng thì giữ nghề gặp đầu tiên"""
    result: dict[str, str] = {}
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for info in data["characters"].values():
            result.setdefault(info["name"], info["profession"])
    return dict(sorted(result.items()))


def save_preview(chars: dict[str, str], size: int, out: Path) -> None:
    """Ghép mọi avatar thành một ảnh lưới, dưới mỗi ảnh ghi tên, giới tính và nghề"""
    rows = (len(chars) + PREVIEW_COLS - 1) // PREVIEW_COLS
    sheet = pygame.Surface((PREVIEW_COLS * size, rows * (size + LABEL_H)))
    sheet.fill((220, 203, 168))
    font = pygame.font.SysFont(None, 18)
    for i, (name, prof) in enumerate(chars.items()):
        x, y = (i % PREVIEW_COLS) * size, (i // PREVIEW_COLS) * (size + LABEL_H)
        sheet.blit(get_avatar(name, prof, size), (x, y))
        for j, line in enumerate((f"{name} ({guess_gender(name)})", prof)):
            text = font.render(line, True, (52, 39, 31))
            sheet.blit(text, text.get_rect(midtop=(x + size // 2, y + size + 2 + j * 15)))
    pygame.image.save(sheet, str(out))


def main() -> None:
    ap = argparse.ArgumentParser(description="Xuất avatar nhân vật từ puzzle JSON")
    ap.add_argument("puzzles", nargs="*", help="File puzzle; bỏ trống = mọi file trong puzzles/")
    ap.add_argument("--size", type=int, default=128, help="Cạnh ảnh (px)")
    ap.add_argument("--png", action="store_true", help=f"Ghi <tên>.png vào {AVATAR_DIR.relative_to(SOURCE_DIR)}")
    ap.add_argument("--preview", default="avatars_preview.png", help="File ảnh xem trước")
    args = ap.parse_args()

    paths = args.puzzles or sorted(glob.glob(str(SOURCE_DIR / "puzzles" / "*" / "*.json")))
    chars = collect_characters(paths)
    pygame.init()
    try:
        save_preview(chars, args.size, Path(args.preview))
        print(f"Preview {len(chars)} nhân vật -> {args.preview}")
        if args.png:
            AVATAR_DIR.mkdir(parents=True, exist_ok=True)
            for name, prof in chars.items():
                target = AVATAR_DIR / f"{name.lower()}.png"
                if target.exists():          # không ghi đè ảnh đã sửa tay
                    print(f"  bỏ qua {target.name} (đã có)")
                    continue
                pygame.image.save(get_avatar(name, prof, args.size), str(target))
            print(f"PNG -> {AVATAR_DIR}")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
