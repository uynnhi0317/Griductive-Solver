"""
Thống kê hiệu năng của SAT solver

Quy ước đếm:
+ decisions: mỗi lần chọn giá trị cho một biến để rẽ nhánh
+ propagations: mỗi biến bị ép giá trị bởi unit propagation
+ backtracks: mỗi lần hoàn tác một decision vì nhánh đó thất bại
+ runtime: thời gian chạy của lệnh solve, tính bằng giây
"""

from dataclasses import dataclass


@dataclass
class SolverStats:
    decisions: int = 0
    propagations: int = 0
    backtracks: int = 0
    runtime: float = 0.0

    def as_dict(self) -> dict[str, float]:
        """Khóa ổn định để ghi CSV"""
        return {
            "decisions": self.decisions,
            "propagations": self.propagations,
            "backtracks": self.backtracks,
            "runtime": self.runtime,
        }

    def merge(self, other: "SolverStats") -> None:
        """Cộng dồn số liệu của một truy vấn khác"""
        self.decisions += other.decisions
        self.propagations += other.propagations
        self.backtracks += other.backtracks
        self.runtime += other.runtime

    def __str__(self) -> str:
        return (
            f"{self.decisions} decisions, {self.propagations} propagations, "
            f"{self.backtracks} backtracks, {self.runtime * 1000:.2f} ms"
        )
    