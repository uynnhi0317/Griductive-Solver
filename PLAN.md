# Griductive-Solver

## Tổng quan

**Griductive-Solver** là hệ thống giải đố và mô phỏng trò chơi logic suy luận suy diễn lưới **Griductive** (thể loại Grid Deduction / Detective Logic Puzzle). 
Trò chơi diễn ra trên một lưới các nhân vật (kích thước 3x3, 4x4, 5x5, ...), trong đó mỗi người bí mật mang một trong hai vai trò: **Tội phạm (Criminal)** hoặc **Vô tội (Innocent)**.

### Luật chơi & Cơ chế cốt lõi:
1. **Manh mối (Clues):** Mỗi phát biểu trên thẻ nhân vật là sự thật 100%. Luôn tồn tại **duy nhất một lời giải hợp lệ** cho toàn bộ bảng.
2. **Lật thẻ tuần tự (Progressive Reveal):** Khi người chơi hoặc hệ thống xác định chính xác vai trò của một nhân vật, thẻ của nhân vật đó sẽ lật mở để hé lộ manh mối tiếp theo.
3. **Quy tắc không đoán mò (No Guessing Rule):** Trò chơi đảm bảo giải được hoàn toàn bằng suy luận logic hình thức. Mọi bước đi đều phải tất suy (entailed) từ các manh mối đã biết. Nếu người chơi đưa ra phán quyết khi chưa đủ bằng chứng logic, hệ thống sẽ từ chối (`NOT_PROVABLE`).

### Kiến trúc phân tầng & Nguyên lý thiết kế:
Dự án tuân thủ nghiêm ngặt nguyên lý **Phân tách trách nhiệm (Separation of Concerns - SoC)**:
- **`game/` (Domain Model thuần túy):** Chỉ chứa mô hình dữ liệu bàn cờ, nhân vật, vùng không gian (Region), định nghĩa manh mối và bộ đánh giá ngữ nghĩa thuần (`semantics.py`), hoàn toàn **KHÔNG** phụ thuộc vào SAT hay Solver.
- **`engine/` (Game Engine):** Nắm giữ "thế giới thực" (Ground Truth: đáp án ẩn và các clue chưa lộ), quản lý vòng đời ván chơi, kiểm duyệt phán quyết (`ACCEPTED`, `NOT_PROVABLE`, `CONTRADICTED`) và lật mở thẻ.
- **`logic/` (Biểu diễn & Mã hóa CNF):** Chịu trách nhiệm mô hình hóa mệnh đề logic, ánh xạ biến hai chiều xác định (`VariableMap`), mã hóa ràng buộc số lượng (`Cardinality`), chuyển đổi các mẫu manh mối sang CNF (`ClueEncoder`), và xây dựng cơ sở tri thức hiện hành $KB_t$ (`KBBuilder`).
- **`solver/` (SAT Solver độc lập):** Bộ giải SAT dựa trên thuật toán **DPLL** hoàn toàn độc lập với bài toán game, hỗ trợ Unit Propagation, Backtracking, Heuristics chọn biến, và thống kê hiệu năng chi tiết (`SolverStats`).
- **`agent/` (Logic Agent):** Bộ não suy diễn tự động chỉ tương tác thông qua `PublicState` (chỉ nhìn thấy manh mối đã lộ và phán quyết đã chứng minh), kiểm tra tất suy bằng 2 truy vấn SAT ($KB \land \neg C_i$ và $KB \land C_i$), ghi lại vết suy diễn (`trace.py`) và kiểm tra tính duy nhất nghiệm (`uniqueness.py`).
- **`gui/` (Pygame GUI):** Giao diện đồ hoạ tương tác, hiển thị trực quan bàn cờ, thẻ nhân vật, highlight vùng ảnh hưởng của manh mối (`CluePanel`), và các chế độ chơi / gợi ý / tự động giải.
- **`experiments/` (Thực nghiệm & Đánh giá):** Chạy benchmark tự động trên các bộ câu đố 3x3, 4x4, 5x5 (stress test), ghi nhận đầy đủ cả trường hợp thành công, thất bại và timeout.

---

## Cấu trúc dự án

```text
Griductive-Solver/
├── .gitignore                          # Bỏ qua file rác, bytecode, cache, kết quả thử nghiệm
├── requirements.txt                    # Dependencies cấp root (tham chiếu tới Source/requirements.txt)
├── README.md                           # Giới thiệu tổng quan và hướng dẫn nhanh
├── PLAN.md                             # Tài liệu kiến trúc, kế hoạch phát triển và quy tắc Git
└── Source/
    ├── main.py                         # Điểm khởi chạy chính của ứng dụng (GUI, CLI, Solver)
    ├── README.md                       # Hướng dẫn chi tiết về mã nguồn
    ├── requirements.txt                # Danh sách thư viện Python phụ thuộc
    │
    ├── game/                           # Mô hình dữ liệu thuần, KHÔNG biết gì về SAT
    │   ├── __init__.py
    │   ├── board.py                    # Lưới NxN, ô, đặt tên ô (A1, C2...)
    │   ├── character.py                # Tên, nghề, status
    │   ├── region.py                   # Row, Column, Neighbors, ExplicitList (+ mở rộng: giao, hàng xóm chung, biên, góc...)
    │   ├── clue.py                     # Dataclass 6 clue lõi + extension, validate tham số/vùng
    │   ├── semantics.py                # Semantic evaluator: clue + assignment đầy đủ -> True/False (không gọi CNF)
    │   ├── public_state.py             # PublicState: chỉ clue đã lộ + verdict đã chứng minh
    │   └── puzzle_loader.py            # Đọc JSON, tách thành PuzzleFull (cho engine) và dữ liệu public
    │
    ├── engine/                         # Game Engine: sở hữu đáp án ẩn và clue chưa lộ
    │   ├── __init__.py
    │   └── game_engine.py              # submit_verdict, reveal, restart; trả ACCEPTED / NOT_PROVABLE / CONTRADICTED
    │
    ├── logic/                          # Chỉ lo biểu diễn logic và mã hoá CNF
    │   ├── __init__.py
    │   ├── cnf.py                      # Literal, Clause, CNF (kiểu dữ liệu dùng chung với solver)
    │   ├── variable_map.py             # Ánh xạ xác định: nhân vật <-> biến C_i; tách biến phụ khỏi biến chính
    │   ├── cardinality.py              # Mã hoá EXACTLY/AT_LEAST/AT_MOST (combinatorial)
    │   ├── clue_encoder.py             # Clue -> CNF cho từng template (dispatch theo loại clue)
    │   ├── kb_builder.py               # KB_t = CNF(clue đã lộ) ∧ unit clause verdict đã chứng minh
    │   └── encoding_stats.py           # Số biến chính, biến phụ, mệnh đề
    │
    ├── solver/                         # SAT solver, độc lập hoàn toàn với game
    │   ├── __init__.py
    │   ├── dpll.py                     # Unit propagation, conflict, chọn biến xác định, backtracking, (pure literal tuỳ chọn)
    │   ├── heuristics.py               # Chiến lược chọn biến (tuỳ chọn)
    │   └── stats.py                    # SolverStats: decisions, propagations, backtracks, runtime
    │
    ├── agent/                          # Logic Agent: chỉ nhận PublicState
    │   ├── __init__.py
    │   ├── entailment.py               # classify(i) -> CRIMINAL / INNOCENT / UNKNOWN / INCONSISTENT (KB ∧ ¬C_i, KB ∧ C_i)
    │   ├── logic_agent.py              # Vòng lặp suy diễn, chọn verdict ép buộc theo row-major, hint
    │   ├── uniqueness.py               # Kiểm tra puzzle có đúng một nghiệm (độc lập với vòng lặp chính)
    │   └── trace.py                    # Deduction trace: bước, clue đang dùng, SAT queries, verdict, clue mới lộ
    │
    ├── gui/                            # Giao diện đồ hoạ Pygame
    │   ├── __init__.py
    │   ├── app.py                      # Vòng lặp ứng dụng Pygame, điều phối màn hình
    │   ├── board_view.py               # Lưới, toạ độ, thẻ úp/lật, hiệu ứng
    │   ├── character_card.py           # Hiển thị thẻ nhân vật (thông tin, màu sắc, role)
    │   ├── clue_panel.py               # Bảng manh mối, chọn clue -> highlight ô/vùng liên quan
    │   ├── control.py                  # Thanh công cụ: Load, Restart, Hint, Auto Solve, nút Criminal/Innocent
    │   └── assets/                     # Tài nguyên đồ họa, font chữ, âm thanh
    │
    ├── puzzles/                        # Dữ liệu các câu đố theo định dạng JSON
    │   ├── 3x3/                        # Câu đố kích thước 3x3 (nhập môn, test nhanh)
    │   ├── 4x4/                        # Câu đố kích thước 4x4 (chuẩn)
    │   └── 5x5/                        # Câu đố kích thước 5x5 (stress case)
    │
    ├── experiments/                    # Đánh giá hiệu năng và thực nghiệm
    │   ├── __init__.py
    │   ├── metrics.py                  # Đo lường thời gian, bộ nhớ (psutil), thống kê solver/encoding
    │   ├── run_benchmark.py            # Chạy benchmark tự động, ghi nhận cả failure/timeout (không loại bỏ)
    │   └── results/                    # Lưu kết quả xuất ra (CSV, biểu đồ so sánh)
    │
    └── tests/                          # Bộ kiểm thử tự động (pytest)
        ├── __init__.py
        └── (unit tests cho từng module: game, logic, solver, agent, engine)
```

---

## Quy tắc làm việc với Git

### 1. Quy tắc đặt tên nhánh

Sử dụng định dạng: `<loại>/<mô-tả-ngắn>`

| Tiền tố (prefix) | Mục đích | Ví dụ |
|---|---|---|
| `feat/` | Thêm chức năng mới | `feat/dpll-solver`, `feat/cardinality-encoding`, `feat/clue-highlight` |
| `fix/` | Sửa lỗi | `fix/engine-provable-check`, `fix/cnf-clause-conflict` |
| `ref/` | Tái cấu trúc code (không đổi hành vi) | `ref/variable-map-dispatch`, `ref/semantics-evaluator` |
| `test/` | Thêm / sửa unit test | `test/entailment-cases`, `test/dpll-backtrack` |
| `docs/` | Cập nhật tài liệu | `docs/update-architecture-plan` |
| `exp/` | Thử nghiệm benchmark / phân tích | `exp/5x5-stress-benchmark` |

**Quy tắc chung:**
- Viết **lowercase**, dùng dấu gạch ngang `-` để phân tách từ
- Mô tả **ngắn gọn, rõ ràng**
- **Không** dùng dấu cách, ký tự đặc biệt, tiếng Việt có dấu
- Ví dụ hợp lệ: `feat/logic-agent-loop`, `fix/pure-literal-bug`
- Ví dụ **không** hợp lệ: `Feat/Add DPLL`, `fix_bug`, `nhanh-moi`

### 2. Luồng làm việc với nhánh

```text
main
 ├── feat/game-semantics
 ├── feat/cardinality-encoder
 ├── feat/dpll-solver
 ├── feat/agent-entailment
 └── feat/gui-clue-highlight
```

- **`main`**: Nhánh chính duy nhất, chứa code ổn định và mới nhất của dự án
- **Feature/fix branches**: Tạo từ `main`, mở Pull Request để merge lại vào `main` khi hoàn thành

**Quy trình chuẩn:**

```bash
# 1. Cập nhật main và tạo nhánh mới
git checkout main
git pull origin main
git checkout -b feat/ten-tinh-nang

# 2. Code & commit thường xuyên theo đúng chuẩn
git add .
git commit -m "feat(scope): mô tả ngắn gọn"

# 3. Đẩy nhánh lên remote repository
git push origin feat/ten-tinh-nang

# 4. Tạo Pull Request vào main, chờ đồng đội review và merge

# 5. Sau khi merge, dọn dẹp nhánh cục bộ
git checkout main
git pull origin main
git branch -d feat/ten-tinh-nang
```

### 3. Quy tắc viết commit message

Sử dụng format: `<type>: <mô tả ngắn>` hoặc `<type>(<scope>): <mô tả ngắn>`

#### Các `type` được sử dụng

| Type | Ý nghĩa | Ví dụ |
|---|---|---|
| `feat` | Thêm chức năng mới | `feat(solver): implement DPLL with unit propagation` |
| `fix` | Sửa lỗi | `fix(engine): fix invalid NOT_PROVABLE verdict check` |
| `refactor` | Tái cấu trúc code (không đổi hành vi) | `refactor(logic): separate auxiliary from core variables` |
| `test` | Thêm / sửa test | `test(agent): add test cases for uniqueness checker` |
| `docs` | Cập nhật tài liệu | `docs: update PLAN.md with new module layout` |
| `style` | Format code, chỉnh khoảng trắng (không đổi logic) | `style: apply PEP8 formatting to board.py` |
| `chore` | Cập nhật cấu hình, dependencies | `chore: add tabulate to requirements.txt` |
| `perf` | Cải thiện hiệu năng xử lý | `perf(solver): optimize watch literals and propagation` |

#### Bảng `scope` (phạm vi mô-đun)

| Scope | Áp dụng cho |
|---|---|
| `game` | Module `game/` (board, character, region, clue, semantics, public_state, loader) |
| `engine` | Module `engine/` (game_engine, submit_verdict, reveal) |
| `logic` | Module `logic/` (cnf, variable_map, cardinality, clue_encoder, kb_builder, stats) |
| `solver` | Module `solver/` (dpll, heuristics, stats) |
| `agent` | Module `agent/` (entailment, logic_agent, uniqueness, trace) |
| `gui` | Module `gui/` (app, board_view, character_card, clue_panel, control) |
| `puzzle` | Dữ liệu các câu đố trong `puzzles/` |
| `exp` | Module `experiments/` (metrics, run_benchmark, results) |
| `test` | Module `tests/` |
| *(bỏ trống)* | Thay đổi cấu hình chung toàn dự án |

#### Ví dụ commit message tốt:

```bash
# Thêm tính năng với scope rõ ràng
git commit -m "feat(game): implement region and semantics evaluator"
git commit -m "feat(logic): implement combinatorial cardinality encoder"
git commit -m "feat(agent): implement entailment classification with SAT queries"
git commit -m "feat(gui): highlight related cells on clue selection"

# Sửa lỗi
git commit -m "fix(engine): return NOT_PROVABLE when evidence is insufficient"

# Thực nghiệm
git commit -m "exp(benchmark): log timeouts and failures on 5x5 stress puzzles"
```

#### Ví dụ commit message **không tốt**:

```bash
# ❌ Quá mơ hồ
git commit -m "fix bug"
git commit -m "update code"

# ❌ Viết sai quy cách (viết hoa, có dấu chấm ở cuối)
git commit -m "Fixed DPLL solver."
git commit -m "Updated gui"

# ❌ Gộp nhiều nội dung không liên quan
git commit -m "add cardinality, fix board view, update README"
```

---

## Phân công nhiệm vụ

Bảng phân công chi tiết theo từng thành viên sẽ được cập nhật và theo dõi trên Google Sheets / GitHub Projects của nhóm.

---

## Hướng dẫn chạy dự án

### 1. Cài đặt môi trường ảo

```bash
# Tạo môi trường ảo
python -m venv .venv

# Kích hoạt môi trường ảo
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Cài đặt toàn bộ thư viện cần thiết
pip install -r requirements.txt
```

### 2. Chạy ứng dụng giao diện (GUI)

```bash
cd Source
python main.py
```

### 3. Chạy kiểm thử tự động (Unit Tests)

```bash
cd Source
python -m pytest tests/ -v
```

### 4. Chạy thực nghiệm & Benchmark

```bash
cd Source
# Chạy benchmark trên toàn bộ các bộ câu đố (3x3, 4x4, 5x5)
python -m experiments.run_benchmark
```