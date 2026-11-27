# Griductive Solver

> Đồ án 2 môn **CSC14003 – Cơ sở Trí tuệ nhân tạo** · Trường Đại học Khoa học tự nhiên, ĐHQG-HCM

Bản cài đặt lại trò chơi **Griductive** (Grid Deduction Logic Puzzle) sử dụng thuật toán **DPLL (SAT Solver)** và giao diện đồ họa **Pygame**.

**Video demo:** <Link>
<!-- [[24_21] Demo Project 2 - Griductive Solver | Môn Cơ sở Trí tuệ nhân tạo | Nhóm 16](https://www.youtube.com/watch?v=) -->

## Mục lục
- [1. Giới thiệu](#1-giới-thiệu) 
- [2. Tính năng](#2-tính-năng)
- [3. Cài đặt & chạy](#3-cài-đặt--chạy)
- [4. Cấu trúc thư mục](#4-cấu-trúc-thư-mục) 
- [5. Thành viên](#5-Thành-viên) 
- [6. Tham khảo](#6-tham-khảo)

## 1. Giới thiệu

**Griductive** là trò chơi giải đố suy luận trên lưới. Một lưới gồm các nghi phạm, mỗi người bí mật là tội phạm (CRIMINAL) hoặc vô tội (INNOCENT) — mọi manh mối được tiết lộ trên thẻ của họ đều là sự thật, với duy nhất một lời giải phù hợp với tất cả các manh mối đó.

Khi đưa ra phán quyết chính xác về một nghi phạm, thẻ sẽ được lật mở để tiết lộ một phát biểu mới, giúp bạn từng bước phá giải vụ án thông qua suy luận.

Dự án gồm: game với giao diện đồ họa, solver (DPLL), và bộ thực nghiệm so sánh hiệu năng.

## 2. Tính năng
**Gameplay:** Chọn một thẻ nghi phạm để đưa ra phán quyết. Phán quyết đúng sẽ lật thẻ, hiện ra manh mối mới. Chọn **Hint** để xem gợi ý, **Auto Solve** để chạy tự động giải. Danh sách manh mối, lịch sử chơi, và số liệu được hiển thị trong tab bên tay phải của màn hình game.

**Điều khiển**
<div align="center">

| Thao tác trên giao diện| Phím | Chức năng |
|---|---|---|
| Click chuột | Mũi tên | Chọn thẻ |
| Nhấn INNOCENT / CRIMINAL | C / I | Ra phán quyết |
| Nhấn Hint | H | Hiện gợi ý |
| Nhấn Auto Solve / Stop | A | Tự động giải / Tạm dừng |
| Nhấn Previous / Next Stage | PgUp / PgDn | Chọn màn trước / sau |
| Nhấn Load | L | Tải một màn chơi |
| _ | F1 | Hiện hướng dẫn điều khiển |

</div>

## 3. Cài đặt & chạy
### Yêu cầu
- Python 3.10 – 3.12
- Các thư viện trong `requirements.txt` (pygame, numpy, pandas, matplotlib, psutil, tabulate, pytest)

### Cài đặt
**Clone repo**
```bash
git clone https://github.com/uynnhi0317/Griductive-Solver.git
cd Griductive-Solver/Source
```
**Tạo và kích hoạt môi trường ảo**
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows
# source .venv/bin/activate     # macOS / Linux
```
**Cài đặt thư viện**
```bash
pip install -r requirements.txt
```
### Chạy chương trình
> Chạy các lệnh sau khi đứng từ thư mục Source/ của dự án

**Trò chơi**
```bash
python main.py 
```
**Test - Kiểm tra logic game và thuật giải**
```bash
python -m pytest tests/ -v
```
**Benchmark - Đo số liệu các thuật giải và vẽ biểu đồ**
```bash 
python -m experiments.run_benchmark             # Đo số liệu
python -m experiments.plot_results              # Vẽ biểu đồ
```

## 4. Cấu trúc thư mục
```
Griductive-Solver
│   .gitignore
│   PLAN.md
└───Source                          # Mã nguồn dự án
    │   main.py
    │   README.md
    │   requirements.txt
    ├───engine                      # Game Engine: giữ đáp án ẩn, phán xử verdict
    ├───agent                       # Logic Agent: suy diễn tất suy, hint, trace
    ├───experiments                 # Scripts đo đạc các thuật giải và trực quan hóa dữ liệu
    ├───game                        # Mô hình dữ liệu
    ├───gui                         # Đồ họa, hoạt ảnh
    ├───logic                       # Biểu diễn logic mệnh đề
    ├───puzzles                     # Bộ câu đố
    ├───solver                      # Thuật toán giải màn chơi
    └───tests                       # Scripts kiểm tra các tính năng của dự án
```

## 5. Thành viên
<div align="center">

| Họ tên | MSSV | GitHub |
|---|---|---|
| Hoàng Diễm Phương | 24120125 | [dp-24ctt3](https://github.com/dp-24ctt3)|
| Dương Ngọc Minh Thư | 24120144 | [dnmthuw](https://github.com/dnmthuw)|
| Trần Ngô Uyên Nhi | 24120210 | [uynnhi0317](https://github.com/uynnhi0317)|
| Trần Tuấn Kiệt | 24120359 | [tkiet06-us](https://github.com/tkiet06-us)|

</div>

## 6. Tham khảo
- Griductive – Daily Grid-Deduction Puzzle: https://knotwise.games/games/griductive
