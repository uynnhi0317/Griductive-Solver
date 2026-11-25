"""Hộp thoại hệ điều hành dùng cho nút Load. Tách riêng để test có thể thay thế bằng hàm giả."""

from pathlib import Path


class DialogUnavailable(RuntimeError):
    """Môi trường không mở được hộp thoại (thiếu tkinter hoặc không có màn hình)"""


def ask_puzzle_path(initial_dir: Path) -> Path | None:
    """
    Mở hộp thoại chọn file puzzle JSON; trả về None nếu người dùng bấm Cancel.
    Chạy đồng bộ: cửa sổ game đứng yên trong lúc hộp thoại mở.
    """
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError as exc:
        raise DialogUnavailable("tkinter is not installed") from exc

    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:
        raise DialogUnavailable(str(exc)) from exc
    root.withdraw()
    root.attributes("-topmost", True)       # không để hộp thoại chìm sau cửa sổ pygame
    try:
        chosen = filedialog.askopenfilename(
            parent=root,
            title="Load puzzle",
            initialdir=str(initial_dir),
            filetypes=[("Puzzle JSON", "*.json"), ("All files", "*.*")],
        )
    finally:
        root.destroy()
    return Path(chosen) if chosen else None