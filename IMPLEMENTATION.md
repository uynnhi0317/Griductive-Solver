# Griductive Solver — project handoff

Tài liệu này là bản đồ ngắn để agent tiếp tục công việc mà không cần nạp toàn bộ repository. Trạng thái bên dưới dựa trên code hiện tại; `PLAN.md` là tài liệu thiết kế dài hơn, không nên hiểu mọi module được nhắc trong đó là đã hoàn thành. PDF đề bài chưa đọc được trong môi trường này nên các yêu cầu bên dưới không đại diện cho việc đối chiếu PDF.

## Trạng thái trong một câu

Domain model và puzzle JSON loader đã có; CNF, variable map và encoding stats đã có nền tảng. Solver, clue encoding, agent, engine, GUI và chương trình chạy chính hiện chưa được triển khai.

## Bản đồ repository

```text
Source/
├── main.py                   # Entry point, hiện rỗng
├── game/                     # Domain model, clue, semantics, loader, public state
├── logic/                    # CNF, variable map, encoding stats; phần encoder còn rỗng
├── solver/                   # DPLL/heuristics/stats — file rỗng
├── agent/                    # entailment/logic agent/uniqueness/trace — file rỗng
├── engine/                   # game_engine.py — rỗng
├── gui/                      # Các module Pygame — rỗng
├── experiments/              # benchmark/metrics — rỗng
├── puzzles/3x3/              # Bốn puzzle JSON mẫu
├── puzzles/4x4/, puzzles/5x5/ # Chưa có puzzle
├── tests/                    # Hiện chỉ có test_semantics.py
└── requirements.txt          # Dependencies Python
```

Ở root có `PLAN.md` mô tả kiến trúc dự kiến và `IMPLEMENTATION.md` này mô tả hiện trạng. Không có entry point chạy game khả dụng cho tới khi `Source/main.py` và các tầng còn thiếu được nối lại.

## Những phần đã triển khai

### `Source/game/` — domain và dữ liệu

- `cell.py`, `character.py`, `board.py`: tọa độ `A1`, nhân vật, role `CRIMINAL`/`INNOCENT`, board vuông kích thước 1–5. Thứ tự ô là row-major: `A1, B1, …, A2, B2, …`.
- `region.py`: `Row`, `Column`, `Neighbors` (8 hướng, không gồm tâm), `ExplicitList`.
- `clue.py`: sáu clue lõi `FACT`, `SAME`, `DIFFERENT`, `EXACTLY`, `AT_LEAST`, `AT_MOST`; có validate, mô tả và serialize/deserialize qua registry.
- `semantics.py`: kiểm tra một assignment đầy đủ `Cell -> Status` có thỏa clue hay không. Đây là evaluator, không phải bộ tìm nghiệm.
- `puzzle_loader.py`: `load_puzzle(path)` / `parse_puzzle(data)` trả `PuzzleFull`; kiểm tra cấu trúc dữ liệu, tham chiếu ô, clue khớp đáp án và ít nhất một thẻ mở ban đầu. Chưa kiểm tra tính duy nhất hoặc khả năng giải suy diễn.
- `public_state.py`: `PublicState` chỉ giữ các thẻ đã lật cùng verdict/clue tương ứng; `with_verdict` tạo state mới. Thiết kế này là mặt dữ liệu dự kiến cho agent.

`PuzzleFull` chứa đáp án ẩn và toàn bộ clue. Thành phần engine chưa có nên ranh giới giữa `PuzzleFull` và `PublicState` hiện chưa được áp dụng trong luồng chơi.

### `Source/logic/` — SAT representation

- `cnf.py`: CNF với literal số nguyên có dấu; chuẩn hóa clause, bỏ tautology và duplicate, giữ empty clause là UNSAT, xuất DIMACS.
- `variable_map.py`: biến chính `1..N*N` theo row-major; `True` nghĩa là criminal, `False` là innocent. Biến phụ được cấp sau biến chính; `decode(model)` giải mã assignment.
- `encoding_stats.py`: thống kê biến, clause, unit clause và độ dài clause lớn nhất.
- `cardinality.py`, `clue_encoder.py`, `kb_builder.py`: hiện rỗng. Chưa có đường chuyển clue hoặc public state thành CNF/KB.

## Module chưa có implementation

| Module | File hiện rỗng | Việc cần làm |
|---|---|---|
| SAT solver | `solver/dpll.py`, `heuristics.py`, `stats.py` | DPLL, unit propagation, backtracking, model và thống kê. |
| Agent | `agent/entailment.py`, `logic_agent.py`, `uniqueness.py`, `trace.py` | Kiểm tra entailment, chọn verdict ép buộc, uniqueness và trace. |
| Engine | `engine/game_engine.py` | Giữ ground truth, chấm verdict, mở clue và quản lý ván. |
| GUI | `gui/app.py`, `board_view.py`, `character_card.py`, `clue_panel.py`, `control.py` | Giao diện Pygame. |
| Experiments | `experiments/metrics.py`, `run_benchmark.py` | Benchmark và ghi metrics. |
| Entry point | `main.py` | Khởi chạy ứng dụng sau khi các tầng trên hoạt động. |

## Hợp đồng nối các tầng

```text
Puzzle JSON -> PuzzleFull -> GameEngine -> PublicState -> KBBuilder
                                                    -> ClueEncoder -> CNF
                                                                      -> DPLL
                                                    <- LogicAgent / entailment
```

- `game/` là nguồn chân lý cho ý nghĩa clue; không đưa SAT logic vào domain model.
- `logic/` chuyển domain objects thành CNF và không tự tìm nghiệm.
- `solver/` chỉ nhận CNF, không phụ thuộc game.
- `agent/` chỉ suy luận từ `PublicState`, không đọc solution hoặc clue úp.
- `engine/` mới được giữ `PuzzleFull`, xác thực verdict và tạo `PublicState` kế tiếp.

Quy ước entailment đã được `PLAN.md` mô tả: để xác định role của biến `C_i`, kiểm tra cả `KB ∧ C_i` và `KB ∧ ¬C_i`. Một phía UNSAT chứng minh phía còn lại; cả hai SAT nghĩa là `UNKNOWN`; cả hai UNSAT nghĩa là KB không nhất quán.

## Dữ liệu, test và cách chạy

- Puzzle mẫu: `Source/puzzles/3x3/3x3_01.json` đến `3x3_04.json`. Loader yêu cầu `id`, `size`, `characters`, `solution`, `clues`, `initially_revealed`; `title`/`description` tùy chọn.
- Test hiện có: `Source/tests/test_semantics.py`; chưa có test cho loader, CNF, variable map, solver, agent hay engine.
- Cài dependency và chạy test từ `Source/`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest tests/ -v
```

- `python main.py` hiện chưa chạy ứng dụng vì entry point còn rỗng. Các dependency liệt kê trong `requirements.txt` gồm pytest, pygame, numpy, pandas, matplotlib, psutil và tabulate.

## Điểm bắt đầu đề xuất

1. Bổ sung test cho CNF và `VariableMap`.
2. Cài đặt cardinality encoding, sau đó encoder cho sáu clue; đối chiếu kết quả với `evaluate_clue` bằng các assignment mẫu/exhaustive trên board nhỏ.
3. Dựng KB từ clue trong `PublicState` và các verdict đã chứng minh.
4. Cài DPLL độc lập và test SAT/UNSAT/model trước khi nối agent.
5. Cài entailment, uniqueness, trace và vòng lặp agent; bảo đảm agent chỉ nhận `PublicState`.
6. Cài engine để giữ `PuzzleFull`, rồi mới nối GUI và `main.py`.

Khi thêm loại clue, đồng bộ domain class/registry/serialization, semantic evaluator, CNF encoder và test. Thêm evaluator đơn lẻ không khiến SAT solver hỗ trợ loại clue đó.
