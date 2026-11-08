import re
from dataclasses import dataclass

_CELL_RE = re.compile(r"^([A-Z])([1-9])$")

@dataclass(frozen=True, order=True)
class Cell:
    """
    Một ô trên lưới:
    + row là chỉ số hàng, bắt đầu từ 1 (label: '1')
    + col là chỉ số dòng, bắt đầu từ 1 (label: 'A')
    """
    row: int
    col: int

    @property
    def label(self) -> str:
        """Định dạng nhãn cho một ô"""
        return f"{chr(ord('A') + self.col - 1)}{self.row}"

    @classmethod
    def parse(cls, text: str) -> "Cell":
        """Lấy tọa độ ô"""
        m = _CELL_RE.match(text)
        if not m:
            raise ValueError(f"[Cell]: ID của ô không hợp lệ: {text!r}")
        
        return cls(row=int(m.group(2)), col=ord(m.group(1)) - ord("A") + 1)

    def __str__(self) -> str:
        """Trả về nhãn của ô"""
        return self.label
    