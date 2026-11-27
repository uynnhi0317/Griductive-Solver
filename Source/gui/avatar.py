"""
Avatar nhân vật cho thẻ: sinh SVG theo tên + nghề, rồi nạp thành pygame.Surface

+ Chỉ là phần hiển thị: tên/nghề không mang ý nghĩa logic, nên module này nằm ở gui/ và
  không được game/, engine/, agent/ import
+ Ngẫu nhiên nhưng cố định theo tên (seed = md5(tên)): cùng một tên luôn ra cùng một khuôn mặt
+ Ghép lớp SVG từ sau ra trước: tóc sau -> áo + phụ kiện nghề -> cổ -> tai -> mặt -> mắt/mũi
  -> râu -> miệng -> tóc trước -> mũ
+ Ưu tiên ảnh vẽ tay ở gui/assets/avatars/<tên thường>.png nếu có
"""
import functools
import hashlib
import io
import random
from pathlib import Path

import pygame

AVATAR_DIR = Path(__file__).resolve().parent / "assets" / "avatars"
VIEWBOX = 200
GLASSES_CHANCE = 0.12
BEARD_CHANCE = 0.25
OPEN_EYES_CHANCE = 0.8

# ------------------------------------------------------------------ bảng màu
SKIN = [  # (màu da, màu bóng đổ cho cổ/tai)
    ("#FFDFC8", "#F0C2A6"), ("#F6CBA8", "#E3B08C"), ("#E9B58D", "#D39A72"),
    ("#C98C5F", "#B0744A"), ("#A66A40", "#8C5633"), ("#7D4B2C", "#673C23"),
    ("#5B3621", "#482A1A"),
]
HAIR = ["#1F1A17", "#3B2418", "#6B3E26", "#A0522D", "#C9652B", "#E3B868", "#C9A063", "#9E9E9E"]
EYES = ["#5A3A22", "#2E1E14", "#3C7DC4", "#4C9A5A", "#8E7341", "#6F8090"]
SHIRT = ["#F2B90F", "#1E8E4E", "#C62828", "#F57C1E", "#EC4F9A", "#1E3A8A", "#7B2CBF", "#13897F", "#555555"]

MALE_STYLES = ("short", "spiky", "side", "buzz", "curly")
FEMALE_STYLES = ("long", "bun", "ponytail", "bob")

# Character không có trường giới tính -> tra bảng tên của bộ puzzle (puzzles/*/*.json)
# Thêm puzzle có tên mới thì bổ sung vào đây; tests/test_avatar.py sẽ báo nếu còn thiếu
FEMALE_NAMES = {
    "alice", "anna", "cara", "dina", "eve", "faye", "gina", "hana",
    "ivy", "kara", "maya", "olga", "rosa", "tara", "vera", "xena",
}
MALE_NAMES = {
    "ben", "bob", "cole", "dan", "ezra", "finn", "gus", "hugo", "ian",
    "jack", "liam", "noah", "paul", "quinn", "sam", "umar", "will", "yuri",
}


def guess_gender(name: str) -> str:
    """'F' hoặc 'M'"""
    n = name.strip().lower()
    if n in FEMALE_NAMES:
        return "F"
    if n in MALE_NAMES:
        return "M"
    return "F" if n[-1:] in ("a", "e", "i", "y") else "M"


def shade(hex_color: str, factor: float) -> str:
    """factor < 1: tối đi, factor > 1: sáng lên"""
    rgb = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    if factor <= 1:
        rgb = [int(v * factor) for v in rgb]
    else:
        rgb = [int(v + (255 - v) * (factor - 1)) for v in rgb]
    return "#" + "".join(f"{max(0, min(255, v)):02X}" for v in rgb)


# ------------------------------------------------------------------ tóc
def _hair(style: str, c: str) -> tuple[str, str]:
    """(lớp tóc sau đầu, lớp tóc trước trán)"""
    if style == "short":
        return "", f'<path d="M60 104 C56 62 78 48 100 48 C122 48 144 62 140 104 C138 88 132 78 124 74 C110 80 88 80 76 74 C68 78 62 88 60 104Z" fill="{c}"/>'
    if style == "spiky":
        return "", (f'<path d="M58 98 L56 70 L66 74 L64 50 L78 60 L82 40 L94 54 L102 36 L110 54 L122 40 L124 60 '
                    f'L138 50 L134 74 L144 70 L142 98 C136 82 124 74 100 74 C76 74 64 82 58 98Z" fill="{c}"/>')
    if style == "side":
        return "", f'<path d="M60 102 C54 58 84 44 106 48 C130 50 146 66 140 102 C134 84 128 76 118 72 C100 84 78 86 66 80 C62 86 61 94 60 102Z" fill="{c}"/>'
    if style == "buzz":
        return "", f'<path d="M62 96 C60 62 80 52 100 52 C120 52 140 62 138 96 C132 76 118 68 100 68 C82 68 68 76 62 96Z" fill="{c}"/>'
    if style == "curly":
        bumps = "".join(f'<circle cx="{x}" cy="{y}" r="11" fill="{c}"/>' for x, y in
                        ((64, 88), (68, 70), (80, 57), (95, 52), (110, 52), (124, 58), (134, 70), (137, 88)))
        return "", f'<path d="M62 96 C60 62 80 54 100 54 C120 54 140 62 138 96 C130 76 116 70 100 70 C84 70 70 76 62 96Z" fill="{c}"/>' + bumps
    if style == "long":
        return (f'<path d="M58 100 C48 46 152 46 142 100 L150 170 C130 180 70 180 50 170Z" fill="{c}"/>',
                f'<path d="M60 110 C54 60 80 46 100 48 C120 46 146 60 140 110 C136 86 126 72 104 66 L100 60 L96 66 C74 72 64 86 60 110Z" fill="{c}"/>')
    if style == "bun":
        return (f'<circle cx="100" cy="40" r="17" fill="{c}"/>',
                f'<path d="M61 100 C58 60 80 50 100 50 C120 50 142 60 139 100 C134 80 120 70 100 68 C80 70 66 80 61 100Z" fill="{c}"/>'
                f'<path d="M100 51 L100 66" stroke="{shade(c, 0.75)}" stroke-width="2"/>')
    if style == "ponytail":
        return (f'<path d="M128 66 C164 74 166 132 148 158 C144 132 140 100 124 84Z" fill="{c}"/>',
                f'<path d="M60 104 C56 60 80 48 102 48 C126 48 144 62 140 104 C134 84 124 74 112 70 C96 80 76 82 66 78 C62 86 61 94 60 104Z" fill="{c}"/>')
    if style == "bob":
        return (f'<path d="M56 100 C48 48 152 48 144 100 L146 138 C130 144 70 144 54 138Z" fill="{c}"/>',
                f'<path d="M60 112 C52 58 84 44 104 48 C128 50 148 64 140 112 C136 88 128 76 116 70 C100 82 80 84 68 80 C64 90 61 100 60 112Z" fill="{c}"/>')
    raise ValueError(f"[Avatar]: Kiểu tóc không hợp lệ: {style!r}")


# ------------------------------------------------------------------ áo và phụ kiện trên áo
SHIRT_PATH = "M26 200 C26 174 50 160 100 160 C150 160 174 174 174 200Z"
_TAPE = "M80 162 C78 178 80 190 76 200 M120 162 C122 178 120 190 124 200"

# Mỗi phần là template SVG; {c} = màu truyền theo cú pháp "tên:màu", {skin} = màu bóng của da
PARTS = {
    "vneck": '<path d="M86 160 L100 176 L114 160Z" fill="{skin}"/>',
    "whitev": '<path d="M84 160 L100 200 L116 160Z" fill="#FFFFFF"/>'
              '<path d="M84 160 L96 172 L92 158Z M116 160 L104 172 L108 158Z" fill="#E6E6E6"/>',
    "tie": '<path d="M96 168 L104 168 L106 196 L100 200 L94 196Z" fill="{c}"/>',
    "bowtie": '<path d="M90 166 L100 171 L90 176Z M110 166 L100 171 L110 176Z" fill="{c}"/><circle cx="100" cy="171" r="2.5" fill="{c}"/>',
    "lapels": '<path d="M86 160 L76 200 L64 168Z M114 160 L124 200 L136 168Z" fill="{c}"/>',
    "vest": '<path d="M60 170 C70 166 80 164 86 162 L94 200 L48 200 C50 186 54 176 60 170Z '
            'M140 170 C130 166 120 164 114 162 L106 200 L152 200 C150 186 146 176 140 170Z" fill="{c}"/>',
    "apron": '<path d="M74 172 L126 172 L130 200 L70 200Z" fill="{c}"/>'
             '<path d="M74 172 L82 160 M126 172 L118 160" stroke="{c}" stroke-width="4"/>',
    "overalls": '<path d="M76 178 L124 178 L128 200 L72 200Z" fill="#3E6AA8"/>'
                '<path d="M78 178 L72 162 M122 178 L128 162" stroke="#3E6AA8" stroke-width="6"/>',
    "stripes": '<rect x="66" y="166" width="7" height="34" fill="#ECEFF1"/><rect x="127" y="166" width="7" height="34" fill="#ECEFF1"/>',
    "buttons": '<circle cx="100" cy="182" r="2.6" fill="{c}"/><circle cx="100" cy="192" r="2.6" fill="{c}"/>',
    "dbuttons": "".join(f'<circle cx="{x}" cy="{y}" r="2.2" fill="#9E9E9E"/>' for x in (90, 110) for y in (180, 192)),
    "star": '<polygon points="124,176 127,183 134,183 128,187 130,194 124,190 118,194 120,187 114,183 121,183" fill="{c}"/>',
    "badge": '<path d="M118 176 L130 176 L130 184 C130 189 124 192 124 192 C124 192 118 189 118 184Z" fill="{c}"/>',
    "cross": '<rect x="121" y="176" width="6" height="16" fill="#E53935"/><rect x="116" y="181" width="16" height="6" fill="#E53935"/>',
    "stethoscope": '<path d="M86 164 C82 184 96 188 100 188 M114 164 C118 184 104 188 100 188" stroke="#455A64" stroke-width="3" fill="none"/>'
                   '<circle cx="100" cy="190" r="4.5" fill="#B0BEC5" stroke="#455A64" stroke-width="2"/>',
    "tape": f'<path d="{_TAPE}" stroke="#F2C94C" stroke-width="7" fill="none"/>'
            f'<path d="{_TAPE}" stroke="#5B4A1A" stroke-width="7" stroke-dasharray="1 5" fill="none"/>',
    "jabot": '<path d="M90 160 L100 184 L110 160Z" fill="#FFFFFF"/><path d="M94 166 L106 166 M93 172 L107 172" stroke="#D0D0D0" stroke-width="2"/>',
    "sailorcollar": '<path d="M86 160 L100 180 L114 160Z" fill="#FFFFFF"/>'
                    '<path d="M70 166 L100 196 L130 166 L140 172 L100 200 L60 172Z" fill="#1E3A8A"/>'
                    '<path d="M94 182 L106 182 L100 194Z" fill="#C62828"/>',
    "scarf": '<path d="M84 160 C90 168 110 168 116 160 L118 166 C110 174 90 174 82 166Z" fill="{c}"/><path d="M104 170 L112 186 L104 184Z" fill="{c}"/>',
    "flower": "".join(f'<circle cx="{124 + dx}" cy="{182 + dy}" r="3.2" fill="{{c}}"/>'
                      for dx, dy in ((0, -4), (4, -1), (2.5, 3.5), (-2.5, 3.5), (-4, -1))) +
              '<circle cx="124" cy="182" r="2.2" fill="#F2C94C"/>',
    "note": '<path d="M122 192 L122 178 L132 175 L132 189" stroke="#111111" stroke-width="2.5" fill="none"/>'
            '<circle cx="119.5" cy="192" r="3" fill="#111111"/><circle cx="129.5" cy="189" r="3" fill="#111111"/>',
    "wings": '<path d="M52 180 C56 176 62 177 64 181 C66 177 72 176 76 180 C72 184 66 184 64 184 C62 184 56 184 52 180Z" fill="#F2C94C"/>',
    "pens": '<rect x="68" y="178" width="16" height="13" fill="#000000" opacity=".15"/>'
            '<rect x="71" y="172" width="3" height="10" fill="#1E3A8A"/><rect x="77" y="173" width="3" height="9" fill="#C62828"/>',
    "pocket": '<rect x="116" y="178" width="16" height="13" fill="#000000" opacity=".15"/>',
    "paint": '<circle cx="88" cy="186" r="3" fill="#EC4F9A"/><circle cx="110" cy="190" r="3" fill="#3C7DC4"/><circle cx="100" cy="182" r="2.5" fill="#F2B90F"/>',
    "astro": '<path d="M66 166 C80 176 120 176 134 166 L134 172 C120 184 80 184 66 172Z" fill="#90A4AE"/>'
             '<rect x="120" y="184" width="16" height="10" fill="#3C7DC4"/>',
}

# ------------------------------------------------------------------ mũ / phụ kiện trên đầu
HATS = {
    "chef": '<rect x="74" y="44" width="52" height="18" fill="#FAFAFA"/><circle cx="82" cy="36" r="13" fill="#FAFAFA"/>'
            '<circle cx="100" cy="28" r="15" fill="#FAFAFA"/><circle cx="118" cy="36" r="13" fill="#FAFAFA"/>',
    "pillbox": '<path d="M70 62 L72 38 C86 33 114 33 128 38 L130 62Z" fill="{c}"/><rect x="70" y="54" width="60" height="6" fill="#F2C94C"/>'
               '<path d="M66 62 C80 70 120 70 134 62 L132 66 C118 74 82 74 68 66Z" fill="{dark}"/>',
    "beret": '<ellipse cx="94" cy="54" rx="40" ry="14" fill="{c}" transform="rotate(-10 94 54)"/><circle cx="92" cy="40" r="3" fill="{c}"/>',
    "fedora": '<ellipse cx="100" cy="60" rx="50" ry="9" fill="#4E3B2A"/><path d="M72 60 C72 34 128 34 128 60Z" fill="#5D4632"/>'
              '<rect x="72" y="52" width="56" height="5" fill="#2B1F15"/>',
    "straw": '<ellipse cx="100" cy="62" rx="56" ry="11" fill="#E3C16F"/><path d="M70 62 C70 34 130 34 130 62Z" fill="#D9B45A"/>'
             '<rect x="70" y="54" width="60" height="6" fill="#C62828"/>',
    "hardhat": '<path d="M64 66 C64 34 136 34 136 66Z" fill="{c}"/><rect x="96" y="36" width="8" height="28" rx="3" fill="{dark}"/>'
               '<rect x="58" y="62" width="84" height="7" rx="3" fill="{dark}"/>',
    "police": '<path d="M66 60 C66 40 134 40 134 60Z" fill="{c}"/><rect x="66" y="56" width="68" height="6" fill="#111111"/>'
              '<path d="M70 62 C86 72 114 72 130 62Z" fill="#111111"/><circle cx="100" cy="50" r="4" fill="#F2C94C"/>',
    "kepi": '<path d="M72 62 L74 36 L126 36 L128 62Z" fill="{c}"/><rect x="72" y="54" width="56" height="5" fill="#F2C94C"/>'
            '<path d="M70 62 C86 72 114 72 130 62Z" fill="#111111"/><circle cx="100" cy="46" r="3.5" fill="#F2C94C"/>',
    "pilot": '<path d="M66 60 C66 40 134 40 134 60Z" fill="#1E2A4A"/><rect x="66" y="54" width="68" height="6" fill="#F2C94C"/>'
             '<path d="M70 62 C86 72 114 72 130 62Z" fill="#111111"/>'
             '<path d="M90 46 C94 43 98 44 100 47 C102 44 106 43 110 46 C106 49 102 49 100 49 C98 49 94 49 90 46Z" fill="#F2C94C"/>',
    "sailor": '<path d="M70 58 C70 38 130 38 130 58Z" fill="#FAFAFA"/>'
              '<path d="M62 56 C80 52 120 52 138 56 L136 64 C120 60 80 60 64 64Z" fill="#E0E0E0"/>',
    "ranger": '<ellipse cx="100" cy="60" rx="54" ry="9" fill="#8D6E4E"/><path d="M74 60 L80 34 L100 40 L120 34 L126 60Z" fill="#A1887F"/>'
              '<rect x="74" y="54" width="52" height="5" fill="#4E342E"/>',
    "safari": '<ellipse cx="100" cy="62" rx="52" ry="9" fill="#C8B07A"/><path d="M70 62 C70 32 130 32 130 62Z" fill="#D7C08A"/>'
              '<rect x="70" y="55" width="60" height="5" fill="#6D5038"/>',
    "nurse": '<path d="M74 58 L80 38 L120 38 L126 58Z" fill="#FAFAFA"/>'
             '<rect x="97" y="41" width="6" height="14" fill="#E53935"/><rect x="93" y="45" width="14" height="6" fill="#E53935"/>',
    "flatcap": '<path d="M62 64 C60 42 132 38 140 58 L150 64 C130 70 80 70 62 64Z" fill="{c}"/>',
    "tudor": '<ellipse cx="100" cy="56" rx="46" ry="10" fill="{c}"/><path d="M70 56 C72 38 128 38 130 56Z" fill="{c}"/>'
             '<circle cx="84" cy="50" r="3" fill="#C62828"/><circle cx="92" cy="49" r="3" fill="#FAFAFA"/><circle cx="100" cy="48" r="3" fill="#1E3A8A"/>',
    "goggles": '<path d="M60 70 C80 62 120 62 140 70" stroke="#5D4037" stroke-width="5" fill="none"/>'
               '<circle cx="86" cy="66" r="9" fill="#81D4FA" stroke="#5D4037" stroke-width="3"/>'
               '<circle cx="114" cy="66" r="9" fill="#81D4FA" stroke="#5D4037" stroke-width="3"/>',
    "headset": '<path d="M60 104 C56 44 144 44 140 104" stroke="#333333" stroke-width="5" fill="none"/>'
               '<rect x="54" y="96" width="12" height="20" rx="4" fill="#333333"/><rect x="134" y="96" width="12" height="20" rx="4" fill="#333333"/>'
               '<path d="M60 114 C62 128 76 132 86 128" stroke="#333333" stroke-width="3" fill="none"/><circle cx="87" cy="128" r="3.5" fill="#333333"/>',
    "headband": '<path d="M62 82 C66 56 134 56 138 82" stroke="{c}" stroke-width="6" fill="none"/>'
                '<circle cx="128" cy="64" r="6" fill="{c}"/><circle cx="128" cy="64" r="2.5" fill="#F2C94C"/>',
}

GLASSES = ('<circle cx="86" cy="104" r="8.5" fill="none" stroke="#2B2B2B" stroke-width="2.2"/>'
           '<circle cx="114" cy="104" r="8.5" fill="none" stroke="#2B2B2B" stroke-width="2.2"/>'
           '<path d="M94.5 103 L105.5 103 M77.5 102 L66 99 M122.5 102 L134 99" stroke="#2B2B2B" stroke-width="2"/>')

BEARD = '<path d="M64 108 C66 150 86 154 100 154 C114 154 134 150 136 108 C130 130 116 134 100 134 C84 134 70 130 64 108Z" fill="{c}"/>'


# ------------------------------------------------------------------ nghề -> trang phục
# shirt: 1 màu hoặc tuple màu để chọn ngẫu nhiên (None = SHIRT)
# parts: phụ kiện trên áo theo thứ tự vẽ, "tên" hoặc "tên:màu"
# hat:   None, "tên" hoặc "tên:màu"
# glasses: True => luôn đeo kính
_LAB = ("vneck", "lapels:#E0E0E0")
OUTFITS: dict[str, dict] = {
    "actor":       {"shirt": "#1F1F1F", "parts": ("whitev", "lapels:#000000", "bowtie:#C62828")},
    "artist":      {"parts": ("vneck", "apron:#E8DCC4", "paint"), "hat": "beret"},
    "painter":     {"parts": ("vneck", "apron:#E8DCC4", "paint"), "hat": "beret"},
    "restorer":    {"parts": ("vneck", "apron:#E8DCC4"), "hat": "beret"},
    "astronaut":   {"shirt": "#ECEFF1", "parts": ("astro",)},
    "baker":       {"shirt": "#FAFAFA", "parts": ("vneck", "apron:#F3E2C7"), "hat": "chef"},
    "chef":        {"shirt": "#FAFAFA", "parts": ("vneck", "dbuttons", "scarf:#C62828"), "hat": "chef"},
    "cook":        {"shirt": "#FAFAFA", "parts": ("vneck", "dbuttons", "scarf:#1E3A8A"), "hat": "chef"},
    "builder":     {"shirt": "#F57C1E", "parts": ("vneck", "stripes"), "hat": "hardhat:#F2B90F"},
    "fitter":      {"shirt": ("#F57C1E", "#FFB300", "#13897F"), "parts": ("vneck", "stripes")},
    "engineer":    {"shirt": ("#3E6AA8", "#13897F"), "parts": ("vneck", "pens"), "hat": "hardhat:#FAFAFA"},
    "mason":       {"shirt": ("#9E9E9E", "#8D6E63"), "parts": ("vneck", "apron:#E8DCC4"), "hat": "flatcap:#5D4037"},
    "inventor":    {"shirt": "#FAFAFA", "parts": (*_LAB, "pens"), "hat": "goggles"},
    "cop":         {"shirt": "#1E3A8A", "parts": ("vneck", "badge:#F2C94C", "buttons:#F2C94C"), "hat": "police:#1E3A8A"},
    "guard":       {"shirt": "#263D6B", "parts": ("vneck", "star:#F2C94C"), "hat": "kepi:#263D6B"},
    "warden":      {"shirt": "#546E7A", "parts": ("vneck", "badge:#CFD8DC"), "hat": "police:#37474F"},
    "keeper":      {"shirt": "#6D7F3A", "parts": ("vneck", "pocket"), "hat": "safari"},
    "ranger":      {"shirt": "#6D7F3A", "parts": ("vneck", "badge:#F2C94C"), "hat": "ranger"},
    "pilot":       {"shirt": "#1E2A4A", "parts": ("whitev", "tie:#111111", "wings"), "hat": "pilot"},
    "sailor":      {"shirt": "#FAFAFA", "parts": ("sailorcollar",), "hat": "sailor"},
    "porter":      {"shirt": ("#C62828", "#1E3A8A", "#2E7D32"), "parts": ("vneck", "buttons:#F2C94C"), "hat": "pillbox"},
    "usher":       {"shirt": "#C62828", "parts": ("whitev", "bowtie:#111111", "buttons:#F2C94C"), "hat": "pillbox:#C62828"},
    "valet":       {"shirt": "#7B1F1F", "parts": ("whitev", "bowtie:#111111", "buttons:#F2C94C")},
    "yeoman":      {"shirt": "#B71C1C", "parts": ("jabot", "buttons:#F2C94C"), "hat": "tudor:#1F1F1F"},
    "doctor":      {"shirt": "#FAFAFA", "parts": (*_LAB, "stethoscope")},
    "nurse":       {"shirt": ("#4FC3F7", "#81C784", "#F48FB1"), "parts": ("vneck", "cross"), "hat": "nurse"},
    "healer":      {"shirt": ("#E8DCC4", "#C5E1A5"), "parts": ("vneck", "scarf:#7B2CBF", "cross")},
    "optician":    {"shirt": "#FAFAFA", "parts": _LAB, "glasses": True},
    "lawyer":      {"shirt": ("#37474F", "#1E3A8A", "#3E2723"), "parts": ("whitev", "tie:#C62828", "lapels:#263238")},
    "judge":       {"shirt": "#1F1F1F", "parts": ("jabot",)},
    "clerk":       {"shirt": ("#1E3A8A", "#37474F", "#5D4037"), "parts": ("whitev", "tie:#C62828")},
    "editor":      {"shirt": ("#6D4C41", "#455A64", "#7B2CBF"), "parts": ("vneck",), "glasses": True},
    "interpreter": {"shirt": ("#455A64", "#1E3A8A"), "parts": ("whitev", "lapels:#263238"), "hat": "headset"},
    "detective":   {"shirt": "#8D6E4E", "parts": ("vneck", "lapels:#6D5038"), "hat": "fedora"},
    "farmer":      {"shirt": ("#C62828", "#2E7D32", "#F57C1E"), "parts": ("vneck", "overalls"), "hat": "straw"},
    "gardener":    {"shirt": ("#8BC34A", "#F2B90F"), "parts": ("vneck", "apron:#5D4037"), "hat": "straw"},
    "florist":     {"shirt": ("#F8BBD0", "#C8E6C9"), "parts": ("vneck", "apron:#2E7D32", "flower:#EC4F9A")},
    "hunter":      {"shirt": "#556B2F", "parts": ("vneck", "vest:#F57C1E"), "hat": "flatcap:#F57C1E"},
    "tailor":      {"shirt": ("#5D4037", "#37474F"), "parts": ("whitev", "vest:#263238", "tape")},
    "stitcher":    {"parts": ("vneck", "tape")},
    "quilter":     {"parts": ("vneck", "tape", "flower:#F2B90F")},
    "dancer":      {"shirt": ("#EC4F9A", "#7B2CBF", "#13897F"), "parts": ("vneck",), "hat": "headband:#EC4F9A"},
    "xylophonist": {"parts": ("whitev", "bowtie:#111111", "note")},
}


def _with_color(token: str, rng: random.Random) -> tuple[str, str]:
    """'tên:màu' -> (tên, màu); không ghi màu thì chọn ngẫu nhiên từ SHIRT"""
    name, _, color = token.partition(":")
    return name, color or rng.choice(SHIRT)


def _outfit(profession: str, rng: random.Random, skin_shade: str) -> tuple[str, str, bool]:
    """(lớp áo, lớp mũ, có đeo kính hay không). Nghề lạ -> áo trơn cổ chữ V"""
    spec = OUTFITS.get(profession.strip().lower(), {"parts": ("vneck",)})
    shirt = spec.get("shirt") or SHIRT
    shirt = shirt if isinstance(shirt, str) else rng.choice(shirt)

    body = f'<path d="{SHIRT_PATH}" fill="{shirt}"/>'
    for token in spec.get("parts", ()):
        name, color = _with_color(token, rng)
        body += PARTS[name].format(c=color, skin=skin_shade)

    hat = ""
    if spec.get("hat"):
        name, color = _with_color(spec["hat"], rng)
        hat = HATS[name].format(c=color, dark=shade(color, 0.6))
    return body, hat, bool(spec.get("glasses"))


# ------------------------------------------------------------------ ghép avatar
def avatar_svg(name: str, profession: str, gender: str | None = None, size: int = VIEWBOX, seed: int = 0) -> str:
    """Chuỗi SVG nền trong suốt; size = số pixel khi rasterize (viewBox luôn 200x200)"""
    rng = random.Random(int(hashlib.md5(f"{name.strip().lower()}|{seed}".encode()).hexdigest(), 16))
    gender = (gender or guess_gender(name)).upper()

    skin, skin_shade = rng.choice(SKIN)
    hair = rng.choice(HAIR)
    iris = rng.choice(EYES)
    style = rng.choice(MALE_STYLES if gender == "M" else FEMALE_STYLES)
    open_eyes = rng.random() < OPEN_EYES_CHANCE
    smile_open = rng.random() < 0.5
    beard = gender == "M" and rng.random() < BEARD_CHANCE
    glasses = rng.random() < GLASSES_CHANCE
    hair_back, hair_front = _hair(style, hair)
    body, hat, must_glasses = _outfit(profession, rng, skin_shade)

    if open_eyes:   # lòng trắng + mống mắt + đồng tử + điểm sáng
        eyes = "".join(f'<ellipse cx="{x}" cy="104" rx="5.2" ry="5.8" fill="#FFFFFF"/>'
                       f'<circle cx="{x}" cy="105" r="3.8" fill="{iris}"/><circle cx="{x}" cy="105" r="1.9" fill="#111111"/>'
                       f'<circle cx="{x + 1.3}" cy="103.6" r="1.1" fill="#FFFFFF"/>' for x in (86, 114))
    else:           # nhắm cười
        eyes = "".join(f'<path d="M{x - 5} 105 Q{x} 100 {x + 5} 105" stroke="#3A2A20" stroke-width="2.2" '
                       f'fill="none" stroke-linecap="round"/>' for x in (86, 114))
    if smile_open:
        mouth = ('<path d="M89 122 Q100 136 111 122Z" fill="#7A2E2E"/>'
                 '<path d="M91 123 L109 123 L107 126 L93 126Z" fill="#FFFFFF"/>')
    else:
        mouth = '<path d="M90 124 Q100 132 110 124" stroke="#7A3B2E" stroke-width="2.4" fill="none" stroke-linecap="round"/>'

    layers = (
        hair_back,
        body,
        f'<rect x="86" y="132" width="28" height="34" rx="10" fill="{skin_shade}"/>',
        f'<circle cx="62" cy="106" r="8" fill="{skin_shade}"/><circle cx="138" cy="106" r="8" fill="{skin_shade}"/>',
        f'<ellipse cx="100" cy="100" rx="38" ry="44" fill="{skin}"/>',
        '<ellipse cx="78" cy="118" rx="6" ry="3.5" fill="#F28B82" opacity=".35"/>'
        '<ellipse cx="122" cy="118" rx="6" ry="3.5" fill="#F28B82" opacity=".35"/>',
        f'<path d="M79 94 Q86 89 93 93 M107 93 Q114 89 121 94" stroke="{shade(hair, 0.8)}" stroke-width="3" '
        f'fill="none" stroke-linecap="round"/>',
        eyes,
        GLASSES if (glasses or must_glasses) else "",
        f'<path d="M100 108 Q96 116 100 117 Q103 117 104 115" stroke="{shade(skin, 0.78)}" stroke-width="2" '
        f'fill="none" stroke-linecap="round"/>',
        BEARD.format(c=hair) if beard else "",
        mouth,
        hair_front,
        hat,
    )
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX} {VIEWBOX}" '
            f'width="{size}" height="{size}">' + "".join(layers) + "</svg>")


# ------------------------------------------------------------------ nạp cho pygame
@functools.lru_cache(maxsize=512)
def get_avatar(name: str, profession: str, size: int) -> pygame.Surface | None:
    """
    Surface vuông size x size, có alpha. Thứ tự ưu tiên:
    1. gui/assets/avatars/<tên thường>.png (ảnh vẽ tay)
    2. SVG sinh tự động, vẽ ở 200px rồi smoothscale về size
    Trả về None nếu không nạp được -> thẻ vẫn vẽ chữ như cũ
    """
    if size <= 0:
        return None
    try:
        custom = AVATAR_DIR / f"{name.strip().lower()}.png"
        if custom.is_file():
            img = pygame.transform.smoothscale(pygame.image.load(str(custom)), (size, size))
        else:
            # Rasterize 1:1 với viewBox (200px) rồi tự co: một số bản SDL_image trên Windows bỏ qua
            # viewBox khi width/height khác 200, làm hình bị phóng to và chỉ còn một góc
            data = io.BytesIO(avatar_svg(name, profession).encode("utf-8"))
            img = pygame.image.load(data, "avatar.svg")
            if img.get_size() != (size, size):
                img = pygame.transform.smoothscale(img, (size, size))
    except (pygame.error, OSError):
        return None
    return img.convert_alpha() if pygame.display.get_surface() is not None else img


def clear_cache() -> None:
    get_avatar.cache_clear()
