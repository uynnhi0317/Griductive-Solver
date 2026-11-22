"""
Kiểm thử GUI không cần màn hình (SDL dummy driver): chơi thủ công qua App, đi qua GameEngine thật.
Puzzle được dựng trong thư mục tạm nên không phụ thuộc vào puzzles/ của repo.
"""

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game.cell import Cell
from game.character import Status
from gui import app as app_module
from gui.app import App
from gui.dialogs import DialogUnavailable
from gui.layout import MIN_WINDOW
from gui.theme import clear_caches
from solver.dpll import SolverTimeout
from solver.stats import SolverStats

NAMES = ["Alice", "Bob", "Cara", "Dan", "Eve", "Finn", "Gina", "Hugo", "Ivy"]
JOBS = ["Actor", "Baker", "Chef", "Doctor", "Engineer", "Farmer", "Guard", "Hunter", "Interpreter"]
SOLUTION = [1, 0, 0, 0, 0, 1, 0, 1, 0]       # A1, C2, B3 là tội phạm
A1, B1, C3 = Cell.parse("A1"), Cell.parse("B1"), Cell.parse("C3")


def make_puzzle(puzzle_id: str, title: str) -> dict:
    """3x3 hợp lệ: thẻ mở sẵn B2 nói 'A1 là tội phạm' nên A1 bị ép buộc ngay từ đầu"""
    cells = [f"{chr(65 + c)}{r + 1}" for r in range(3) for c in range(3)]
    clues = {}
    for i, label in enumerate(cells):
        row, col = divmod(i, 3)
        if i % 2 == 0:
            k = sum(SOLUTION[row * 3 + c] for c in range(3))
            clues[label] = {"type": "EXACTLY", "k": k, "region": {"type": "ROW", "number": row + 1}}
        else:
            k = sum(SOLUTION[r * 3 + col] for r in range(3))
            clues[label] = {"type": "AT_LEAST", "k": k, "region": {"type": "COLUMN", "letter": chr(65 + col)}}
    clues["B2"] = {"type": "FACT", "cell": "A1", "status": "CRIMINAL"}
    return {
        "id": puzzle_id, "title": title, "size": 3,
        "characters": {label: {"name": NAMES[i], "profession": JOBS[i]} for i, label in enumerate(cells)},
        "solution": {label: "CRIMINAL" if SOLUTION[i] else "INNOCENT" for i, label in enumerate(cells)},
        "clues": clues,
        "initially_revealed": ["B2"],
    }


@pytest.fixture
def puzzle_dir(tmp_path):
    for n in (1, 2):
        (tmp_path / f"stage{n}.json").write_text(json.dumps(make_puzzle(f"t{n}", f"Stage {n}")), encoding="utf-8")
    return tmp_path


@pytest.fixture
def app(puzzle_dir):
    instance = App(puzzle_root=puzzle_dir)
    pygame.display.set_mode((1920, 1080), pygame.RESIZABLE)
    instance.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=1920, h=1080, size=(1920, 1080)))
    yield instance
    clear_caches()           # font cache sẽ hỏng sau pygame.quit()
    pygame.quit()


# ----------------------------------------------------------------- helpers
def click(app, pos):
    for kind in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        fields = {"pos": pos} if kind == pygame.MOUSEMOTION else {"pos": pos, "button": 1}
        if kind == pygame.MOUSEMOTION:
            fields.update(rel=(0, 0), buttons=(0, 0, 0))
        app.handle_event(pygame.event.Event(kind, **fields))


def click_card(app, cell):
    click(app, app.board.slot_rect(cell).center)


def press(app, key, mod=0):
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def card_face_up(app, cell) -> bool:
    return app.board.cards[cell].model.face_up


# ------------------------------------------------------------------- tests
def test_starts_with_only_initial_card_revealed(app):
    assert len(app.state.cards) == 1
    assert card_face_up(app, Cell.parse("B2"))
    assert not app.actionbar.criminal.enabled          # chưa chọn gì


def test_verdict_buttons_follow_selection(app):
    click_card(app, C3)
    assert app.actionbar.criminal.enabled and app.actionbar.innocent.enabled
    click_card(app, Cell.parse("B2"))                  # thẻ đã lật
    assert not app.actionbar.criminal.enabled
    click_card(app, Cell.parse("B2"))                  # bấm lại để bỏ chọn
    assert app.selected is None


def test_not_provable_is_rejected_and_reveals_nothing(app):
    click_card(app, C3)
    click(app, app.actionbar.criminal.rect.center)
    assert app.statusbar.message.startswith("NOT PROVABLE")
    assert len(app.state.cards) == 1
    assert not card_face_up(app, C3)
    assert app.board.cards[C3].model.clue_text is None  # clue của thẻ úp không bị lộ
    assert app.toasts._toasts[0].message.startswith("NOT PROVABLE")


def test_contradicted_is_rejected_and_reveals_nothing(app):
    click_card(app, A1)
    click(app, app.actionbar.innocent.rect.center)      # A1 thật ra bị ép là Criminal
    assert app.statusbar.message.startswith("CONTRADICTED")
    assert len(app.state.cards) == 1
    assert not card_face_up(app, A1)


def test_accepted_verdict_flips_card_and_adds_clue(app):
    click_card(app, A1)
    click(app, app.actionbar.criminal.rect.center)
    assert app.state.status_of(A1) is Status.CRIMINAL
    assert card_face_up(app, A1)
    assert app.board.cards[A1].model.clue_text                    # clue mới đã lộ trên thẻ
    assert [row.cell for row in app.panel._rows] == [Cell.parse("B2"), A1]
    assert not app.actionbar.criminal.enabled                     # ô đã lật thì không gọi lại được


def test_sat_calls_counter_includes_rejected_verdicts(app):
    click_card(app, C3)
    click(app, app.actionbar.criminal.rect.center)
    assert "SAT calls 0" not in app.topbar.progress_text


def test_keyboard_play(app):
    press(app, pygame.K_RIGHT)                          # chưa chọn gì: chọn A1
    assert app.selected == A1
    press(app, pygame.K_DOWN)
    press(app, pygame.K_UP)
    assert app.selected == A1
    press(app, pygame.K_UP)                             # chặn ở mép lưới
    assert app.selected == A1
    press(app, pygame.K_c)
    assert app.state.status_of(A1) is Status.CRIMINAL
    press(app, pygame.K_c, pygame.KMOD_CTRL)            # Ctrl+C không phải phím tắt
    assert len(app.state.cards) == 2


def test_restart_returns_to_initial_state(app):
    click_card(app, A1)
    click(app, app.actionbar.criminal.rect.center)
    assert len(app.state.cards) == 2
    click(app, app.actionbar._right[2].rect.center)     # Restart
    assert len(app.state.cards) == 1
    assert app.selected is None
    assert not card_face_up(app, A1)
    assert "SAT calls 0" in app.topbar.progress_text


def test_solver_timeout_leaves_state_unchanged(app, monkeypatch):
    def timeout(*_args):
        raise SolverTimeout(SolverStats())
    monkeypatch.setattr(app.engine, "submit_verdict", timeout)
    click_card(app, A1)
    press(app, pygame.K_c)
    assert "timed out" in app.statusbar.message
    assert len(app.state.cards) == 1


def test_stage_navigation_wraps(app):
    press(app, pygame.K_PAGEDOWN)
    assert app.stage_index == 1
    press(app, pygame.K_PAGEDOWN)
    assert app.stage_index == 0
    press(app, pygame.K_PAGEUP)
    assert app.stage_index == 1


def test_load_custom_file(app, tmp_path_factory, monkeypatch):
    custom = tmp_path_factory.mktemp("custom") / "mine.json"
    custom.write_text(json.dumps(make_puzzle("mine", "My Puzzle")), encoding="utf-8")
    monkeypatch.setattr(app_module, "ask_puzzle_path", lambda _dir: custom)
    click(app, app.actionbar._right[3].rect.center)     # Load
    assert app.engine.title == "My Puzzle"
    assert app.stage_index is None
    assert app.topbar.stage_text == "Custom file"
    press(app, pygame.K_PAGEDOWN)                       # từ file ngoài, tiến vào màn đầu
    assert app.stage_index == 0


def test_load_cancel_keeps_current_game(app, monkeypatch):
    click_card(app, A1)
    press(app, pygame.K_c)
    monkeypatch.setattr(app_module, "ask_puzzle_path", lambda _dir: None)
    click(app, app.actionbar._right[3].rect.center)
    assert len(app.state.cards) == 2


def test_load_bad_file_keeps_current_game(app, tmp_path_factory, monkeypatch):
    bad = tmp_path_factory.mktemp("bad") / "broken.json"
    bad.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(app_module, "ask_puzzle_path", lambda _dir: bad)
    click_card(app, A1)
    press(app, pygame.K_c)
    click(app, app.actionbar._right[3].rect.center)
    assert "Could not load" in app.statusbar.message
    assert app.engine.title == "Stage 1"
    assert len(app.state.cards) == 2


def test_load_dialog_unavailable_is_reported(app, monkeypatch):
    def unavailable(_dir):
        raise DialogUnavailable("no display")
    monkeypatch.setattr(app_module, "ask_puzzle_path", unavailable)
    click(app, app.actionbar._right[3].rect.center)
    assert "Cannot open the file dialog" in app.statusbar.message


def test_window_is_clamped_to_minimum_size(app):
    pygame.display.set_mode((300, 300), pygame.RESIZABLE)
    app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=300, h=300, size=(300, 300)))
    assert app.screen.get_size() == MIN_WINDOW