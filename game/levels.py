"""关卡数据定义。

每关用字符串列表表示棋盘，字符含义见 game.core.CHAR_TO_DIR：
    'U' 上 / 'D' 下 / 'L' 左 / 'R' 右，'.' 或空格表示空位。

设计原则：每关都存在合理的通关顺序（已用 find_solution 验证）。
难度逐步提升：第 1 关为教学关，第 4 关含交叉依赖链。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .core import level_is_solvable, find_solution, load_level, DIR_NAME


@dataclass
class Level:
    """单个关卡。"""

    index: int                     # 关卡序号（从 1 开始）
    grid: List[str]                # 棋盘字符串列表
    max_mistakes: int = 3          # 允许的失误次数
    hint: str = ""                 # 关卡提示文案（可选）


LEVELS: List[Level] = [
    Level(
        index=1,
        grid=[
            "R...",
            ".U..",
            "..L.",
            "...D",
        ],
        hint="教学关：四个箭头都朝外，依次点击即可飞出。",
    ),
    Level(
        index=2,
        grid=[
            "L...",
            "....",
            "U.R.",
            "...D",
        ],
        hint="注意：上面的箭头会挡住下面同列的箭头，先想想顺序。",
    ),
    Level(
        index=3,
        grid=[
            "U...R",
            ".....",
            "..D..",
            ".....",
            "U...L",
        ],
        hint="先消除挡住别人的箭头，被挡的箭头才能飞。",
    ),
    Level(
        index=4,
        grid=[
            "U....",
            ".....",
            "U..LR",
            ".....",
            "L....",
        ],
        hint="本关存在纵向与横向的交叉依赖，请先观察再动手。",
    ),
]


def validate_levels(levels: List[Level]) -> bool:
    """验证所有关卡均可通关（开发期自检 + 自动化测试用）。"""
    ok = True
    for lv in levels:
        if not level_is_solvable(lv.grid):
            print(f"[!] 关卡 {lv.index} 无法通关！")
            ok = False
        else:
            rows, cols, arrows = load_level(lv.grid)
            sol = find_solution(arrows, rows, cols)
            order = " -> ".join(f"({a.row},{a.col}){DIR_NAME[a.direction]}" for a in sol)
            print(f"[ok] 关卡 {lv.index}: 共 {len(arrows)} 个箭头，可行顺序: {order}")
    return ok


if __name__ == "__main__":
    validate_levels(LEVELS)
