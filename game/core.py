"""核心游戏逻辑（不依赖 pygame，方便单元测试）。

本模块包含：
- Arrow：箭头数据模型（行、列、方向）
- 方向常量与字符映射
- is_blocked：路径检测（判断箭头前进方向到边界之间是否有其它箭头）
- load_level / find_solution：关卡解析与可解性验证
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# 方向定义
# ---------------------------------------------------------------------------
# 方向用 (dr, dc) 表示：dr 为行方向增量（向下为正），dc 为列方向增量（向右为正）。
UP = (-1, 0)     # 上：行号减小
DOWN = (1, 0)    # 下：行号增大
LEFT = (0, -1)   # 左：列号减小
RIGHT = (0, 1)   # 右：列号增大

DIRECTIONS: List[Tuple[int, int]] = [UP, DOWN, LEFT, RIGHT]

# 关卡字符串 -> 方向 的映射（关卡用单字符描述箭头）
CHAR_TO_DIR: Dict[str, Tuple[int, int]] = {
    "U": UP,
    "D": DOWN,
    "L": LEFT,
    "R": RIGHT,
}

# 方向 -> 字符（反向映射，用于调试/打印关卡）
DIR_TO_CHAR: Dict[Tuple[int, int], str] = {v: k for k, v in CHAR_TO_DIR.items()}

# 方向 -> 中文名称（用于界面/提示）
DIR_NAME: Dict[Tuple[int, int], str] = {
    UP: "上",
    DOWN: "下",
    LEFT: "左",
    RIGHT: "右",
}


@dataclass(frozen=True)
class Arrow:
    """棋盘中的一个箭头。"""

    row: int                 # 所在行（0 起）
    col: int                 # 所在列（0 起）
    direction: Tuple[int, int]  # 朝向，取 UP/DOWN/LEFT/RIGHT 之一

    @property
    def pos(self) -> Tuple[int, int]:
        return (self.row, self.col)


def is_blocked(
    arrow: Arrow,
    occupied: Set[Tuple[int, int]],
    rows: int,
    cols: int,
) -> bool:
    """判断 arrow 前进方向到棋盘边界之间是否被其它箭头阻挡。

    规则（作业基础版）：只需沿箭头方向，判断同一行/列、箭头与边界之间
    是否还存在其它箭头。存在则返回 True（不能飞出），否则返回 False（可飞出）。

    实现：从箭头的下一格开始，沿方向向量逐格推进，直到越界；途中若遇到
    任何一个被占用的格子（occupied 中的其它箭头），即被阻挡。

    参数：
        arrow    : 被点击的箭头
        occupied : 当前棋盘上所有仍在场的箭头位置集合 (row, col)
        rows, cols : 棋盘行数、列数
    """
    dr, dc = arrow.direction
    r, c = arrow.row + dr, arrow.col + dc
    while 0 <= r < rows and 0 <= c < cols:
        if (r, c) in occupied:
            return True
        r += dr
        c += dc
    return False


def load_level(grid: List[str]) -> Tuple[int, int, List[Arrow]]:
    """把字符串关卡解析为 (rows, cols, arrows)。

    关卡用字符串列表表示，每一行字符串的每个字符：
        'U' / 'D' / 'L' / 'R'  -> 对应方向的箭头
        其它字符（如 '.' / ' '） -> 空格
    """
    rows = len(grid)
    cols = max(len(line) for line in grid)
    arrows: List[Arrow] = []
    for r, line in enumerate(grid):
        for c, ch in enumerate(line):
            if ch in CHAR_TO_DIR:
                arrows.append(Arrow(r, c, CHAR_TO_DIR[ch]))
    return rows, cols, arrows


def find_solution(
    arrows: List[Arrow],
    rows: int,
    cols: int,
) -> Optional[List[Arrow]]:
    """寻找一个可行的消除顺序（用于验证关卡可通关）。

    采用带回溯的深度优先搜索：每一步在所有仍可飞出的箭头中任选一个消除，
    直到清空全部箭头。若存在某个顺序能清空，则返回该顺序（列表），否则返回 None。

    注：该函数同时充当「AI 自动求解」的工具，也用于关卡可解性验证。
    """
    occupied: Set[Tuple[int, int]] = {a.pos for a in arrows}
    remaining: List[Arrow] = list(arrows)

    def dfs(occupied: Set[Tuple[int, int]], remaining: List[Arrow],
            path: List[Arrow]) -> Optional[List[Arrow]]:
        if not remaining:
            return path
        # 计算当前所有「可飞出」的箭头
        for idx, a in enumerate(remaining):
            if not is_blocked(a, occupied, rows, cols):
                new_occupied = occupied - {a.pos}
                new_remaining = remaining[:idx] + remaining[idx + 1:]
                res = dfs(new_occupied, new_remaining, path + [a])
                if res is not None:
                    return res
        return None

    return dfs(occupied, remaining, [])


def level_is_solvable(grid: List[str]) -> bool:
    """判断一个字符串关卡是否存在可行通关顺序。"""
    rows, cols, arrows = load_level(grid)
    return find_solution(arrows, rows, cols) is not None
