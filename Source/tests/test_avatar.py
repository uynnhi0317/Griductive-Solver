"""Avatar chỉ là phần hiển thị, test để chắc: cố định theo tên, SVG hợp lệ với mọi nghề trong puzzle"""
import glob
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from gui.avatar import FEMALE_NAMES, MALE_NAMES, OUTFITS, avatar_svg, guess_gender

SOURCE_DIR = Path(__file__).resolve().parent.parent


def _all_characters() -> set[tuple[str, str]]:
    chars = set()
    for path in glob.glob(str(SOURCE_DIR / "puzzles" / "*" / "*.json")):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        chars |= {(c["name"], c["profession"]) for c in data["characters"].values()}
    return chars


def test_same_name_same_avatar():
    assert avatar_svg("Bea", "Clerk") == avatar_svg("Bea", "Clerk")
    assert avatar_svg("Bea", "Clerk") == avatar_svg(" bea ", "Clerk")


def test_seed_changes_avatar():
    assert avatar_svg("Bea", "Clerk", seed=0) != avatar_svg("Bea", "Clerk", seed=1)


def test_size_only_changes_pixels():
    small, big = avatar_svg("Bea", "Clerk", size=64), avatar_svg("Bea", "Clerk", size=256)
    assert 'width="64"' in small and 'width="256"' in big
    assert small.split(">", 1)[1] == big.split(">", 1)[1]      # nội dung vẽ giống hệt


@pytest.mark.parametrize("name, profession", sorted(_all_characters()))
def test_every_puzzle_character_is_valid_svg(name, profession):
    ET.fromstring(avatar_svg(name, profession))


@pytest.mark.parametrize("profession", sorted(OUTFITS) + ["Unknown Job"])
def test_every_outfit_is_valid_svg(profession):
    ET.fromstring(avatar_svg("Alex", profession))


def test_every_puzzle_name_has_gender():
    """Puzzle thêm tên mới mà chưa khai báo giới tính thì test này báo để bổ sung bảng tên"""
    missing = {name for name, _ in _all_characters()} - {n.title() for n in FEMALE_NAMES | MALE_NAMES}
    assert not missing, f"Thêm vào FEMALE_NAMES / MALE_NAMES trong gui/avatar.py: {sorted(missing)}"


def test_guess_gender():
    assert guess_gender("Alice") == "F" and guess_gender("Bob") == "M"
    assert guess_gender("Zelda") == "F" and guess_gender("Brandon") == "M"   # tên lạ: đoán theo chữ cái cuối
