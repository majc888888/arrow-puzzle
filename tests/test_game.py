"""一箭又一箭 —— 逻辑层自动化测试。

覆盖作业要求的 T01~T06 测试项。使用标准库 unittest，无需额外依赖。
运行方式（在项目根目录）：
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

# 使用无窗口驱动，保证测试可在无图形环境运行
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from game.core import (  # noqa: E402
    Arrow, UP, DOWN, LEFT, RIGHT, is_blocked, load_level, find_solution,
    find_next_move,
)
from game.levels import LEVELS  # noqa: E402
from game import ui  # noqa: E402


class PathDetectionTest(unittest.TestCase):
    """T01/T02/T03：路径检测与边界处理。"""

    def test_clear_arrow_is_not_blocked(self):
        """T01：前方无阻挡的箭头应可飞出（is_blocked 返回 False）。"""
        # 单箭头 (1,1) 朝右，右侧为空
        arrow = Arrow(1, 1, RIGHT)
        occupied = {(1, 1)}
        self.assertFalse(is_blocked(arrow, occupied, 3, 3))

    def test_blocked_arrow_is_blocked(self):
        """T02：前方有其它箭头的应被阻挡（is_blocked 返回 True）。"""
        # (0,0) 朝右，但 (0,3) 有箭头挡在中间
        arrow = Arrow(0, 0, RIGHT)
        occupied = {(0, 0), (0, 3)}
        self.assertTrue(is_blocked(arrow, occupied, 4, 4))

    def test_four_directions(self):
        """四个方向的阻挡判断均应正确。"""
        # 上：同一列上方有箭头
        self.assertTrue(is_blocked(Arrow(3, 1, UP), {(0, 1), (3, 1)}, 4, 4))
        # 下：同一列下方无箭头
        self.assertFalse(is_blocked(Arrow(1, 1, DOWN), {(1, 1)}, 4, 4))
        # 左：同一行左侧有箭头
        self.assertTrue(is_blocked(Arrow(1, 3, LEFT), {(1, 0), (1, 3)}, 4, 4))
        # 右：同一行右侧无箭头
        self.assertFalse(is_blocked(Arrow(1, 0, RIGHT), {(1, 0)}, 4, 4))

    def test_edge_arrow_no_out_of_bounds(self):
        """T03：位于边缘且朝向棋盘外的箭头，正常可飞出且不越界。"""
        # 左上角朝上、朝左；右下角朝下、朝右，均贴着边界朝外
        cases = [
            Arrow(0, 0, UP),
            Arrow(0, 0, LEFT),
            Arrow(3, 3, DOWN),
            Arrow(3, 3, RIGHT),
        ]
        occupied = {(0, 0), (3, 3)}
        for a in cases:
            self.assertFalse(is_blocked(a, occupied, 4, 4),
                             f"{a} 应可飞出且不越界")

    def test_blocked_beyond_edge_ignored(self):
        """越界判断只应在棋盘内进行，不应访问越界格子。"""
        # (0,0) 朝上，直接贴边，while 循环应一次都不进入
        arrow = Arrow(0, 0, UP)
        self.assertFalse(is_blocked(arrow, {(0, 0)}, 4, 4))


class LevelSolvabilityTest(unittest.TestCase):
    """T04：所有关卡都应存在通关顺序。"""

    def test_all_levels_solvable(self):
        self.assertGreaterEqual(len(LEVELS), 3, "至少需要 3 个关卡")
        for lv in LEVELS:
            rows, cols, arrows = load_level(lv.grid)
            sol = find_solution(arrows, rows, cols)
            self.assertIsNotNone(sol, f"关卡 {lv.index} 应可通关")
            self.assertEqual(len(sol), len(arrows),
                             f"关卡 {lv.index} 的通关顺序应包含全部箭头")


class GameFlowTest(unittest.TestCase):
    """T02/T05/T06：基于 Game 状态机的完整流程测试。"""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((ui.WINDOW_W, ui.WINDOW_H))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def _new_game(self, level_index=0):
        g = ui.Game(self.screen)
        g.load_level(level_index)
        g.state = ui.STATE_PLAYING   # load_level 仅加载数据，需手动进入游戏状态
        return g

    def _click(self, g, row, col):
        g._click_arrow(row, col)

    def _settle(self, g, seconds):
        g.update(seconds)

    def test_click_clear_arrow_flies_away(self):
        """T01：点击前方无阻挡的箭头，箭头飞出并被移除。"""
        g = self._new_game(0)   # 关卡 1：四个箭头均朝外，无阻挡
        n_before = len(g.arrows)
        # 关卡 1 (0,0) 朝右，无阻挡
        self._click(g, 0, 0)
        self.assertEqual(len(g.arrows), n_before - 1, "箭头应从场上移除")
        self.assertEqual(len(g.flying), 1, "应有一个飞出动画")
        # 动画结束后飞出列表清空
        self._settle(g, ui.FLY_DURATION + 0.1)
        self.assertEqual(len(g.flying), 0)

    def test_click_blocked_arrow_costs_mistake(self):
        """T02：点击前方有阻挡的箭头，箭头不消失且失误次数减 1。"""
        g = self._new_game(1)   # 关卡 2：(2,0) 朝上被 (0,0) 挡住
        n_before = len(g.arrows)
        mistakes_before = g.mistakes
        self._click(g, 2, 0)
        self.assertEqual(len(g.arrows), n_before, "被阻挡的箭头不应消失")
        self.assertEqual(g.mistakes, mistakes_before - 1, "失误次数应减 1")
        self.assertGreaterEqual(len(g.shaking), 1, "应有碰撞晃动动画")

    def test_clear_all_arrows_enters_next_level(self):
        """T04：消除本关全部箭头后显示通关并可进入下一关。"""
        g = self._new_game(0)
        rows, cols, arrows = load_level(LEVELS[0].grid)
        sol = find_solution(arrows, rows, cols)
        for a in sol:
            self._click(g, a.row, a.col)
            self._settle(g, ui.FLY_DURATION + 0.1)
        self.assertEqual(g.state, ui.STATE_CLEAR, "清空后应进入通关状态")
        g._next_level()
        self.assertEqual(g.state, ui.STATE_PLAYING, "点击下一关应回到游戏状态")
        self.assertEqual(g.level_index, 1, "应切换到第 2 关")

    def test_mistakes_exhausted_game_over(self):
        """T05：失误次数耗尽后显示失败。"""
        g = self._new_game(1)   # 关卡 2 默认 3 次失误
        self.assertEqual(g.mistakes, 3)
        # 反复点击被阻挡的 (2,0)，每次先让晃动动画结束
        for _ in range(3):
            self._click(g, 2, 0)
            self._settle(g, ui.SHAKE_DURATION + 0.1)
        self.assertEqual(g.mistakes, 0, "失误次数应耗尽为 0")
        self.assertEqual(g.state, ui.STATE_OVER, "失误耗尽应进入失败状态")

    def test_restart_restores_state(self):
        """T06：游戏进行中重新开始，箭头布局和失误次数恢复。"""
        g = self._new_game(1)
        original_arrows = [(a.row, a.col) for a in g.arrows]
        # 先制造一次失误和一次飞出
        self._click(g, 2, 0)          # 碰撞，扣 1 次失误
        self._settle(g, ui.SHAKE_DURATION + 0.1)
        self._click(g, 0, 0)          # 飞出
        self._settle(g, ui.FLY_DURATION + 0.1)
        self.assertNotEqual(g.mistakes, LEVELS[1].max_mistakes)
        # 重新开始
        g.restart_level()
        self.assertEqual(g.state, ui.STATE_PLAYING)
        self.assertEqual(g.mistakes, LEVELS[1].max_mistakes, "失误次数应恢复")
        restored = [(a.row, a.col) for a in g.arrows]
        self.assertEqual(sorted(restored), sorted(original_arrows),
                         "箭头布局应恢复为初始状态")


class ExtensionFeatureTest(unittest.TestCase):
    """扩展功能：撤销、提示、星级、关卡解锁。"""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((ui.WINDOW_W, ui.WINDOW_H))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def _new_game(self, level_index=0):
        g = ui.Game(self.screen)
        g.load_level(level_index)
        g.state = ui.STATE_PLAYING
        return g

    def _click(self, g, row, col):
        g._click_arrow(row, col)

    def _settle(self, g, seconds):
        g.update(seconds)

    def _clear_level(self, g, level_index):
        """按求解顺序清空指定关卡。"""
        rows, cols, arrows = load_level(LEVELS[level_index].grid)
        for a in find_solution(arrows, rows, cols):
            self._click(g, a.row, a.col)
            self._settle(g, ui.FLY_DURATION + 0.1)

    # ---- 撤销 ----
    def test_undo_restores_fly_out(self):
        """撤销一次成功飞出，箭头应恢复到场上。"""
        g = self._new_game(0)
        n_before = len(g.arrows)
        self._click(g, 0, 0)                       # (0,0) 朝右，可飞
        self._settle(g, ui.FLY_DURATION + 0.1)
        self.assertEqual(len(g.arrows), n_before - 1)
        g.undo()
        self.assertEqual(len(g.arrows), n_before, "撤销后箭头应恢复")
        self.assertEqual(len(g.history), 0, "历史栈应弹出到空")

    def test_undo_restores_mistake(self):
        """撤销一次碰撞，失误次数应恢复。"""
        g = self._new_game(1)
        self._click(g, 2, 0)                       # 碰撞
        self._settle(g, ui.SHAKE_DURATION + 0.1)
        self.assertEqual(g.mistakes, 2)
        g.undo()
        self.assertEqual(g.mistakes, 3, "撤销后失误次数应恢复")

    def test_undo_after_game_over_returns_playing(self):
        """失误耗尽进入失败后，撤销应能回到游戏状态。"""
        g = self._new_game(1)
        for _ in range(3):
            self._click(g, 2, 0)
            self._settle(g, ui.SHAKE_DURATION + 0.1)
        self.assertEqual(g.state, ui.STATE_OVER)
        g.undo()
        self.assertEqual(g.state, ui.STATE_PLAYING, "撤销后应回到游戏状态")
        self.assertEqual(g.mistakes, 1)

    # ---- 提示 ----
    def test_hint_marks_safe_arrow(self):
        """提示应消耗次数并高亮一个确实可飞出的箭头。"""
        g = self._new_game(0)
        hints_before = g.hints_left
        g.use_hint()
        self.assertEqual(g.hints_left, hints_before - 1, "提示次数应减 1")
        self.assertIsNotNone(g.hint_target, "应设置提示目标")
        arrow = g.arrow_at(*g.hint_target)
        self.assertFalse(is_blocked(arrow, g.occupied_positions(),
                                    g.rows, g.cols),
                         "被提示的箭头应确实可飞出")

    def test_hint_exhausted_no_more(self):
        """提示次数用完后，继续请求提示不应再消耗。"""
        g = self._new_game(0)
        for _ in range(3):
            g.use_hint()
        self.assertEqual(g.hints_left, 0)
        g.use_hint()
        self.assertEqual(g.hints_left, 0, "次数用尽后不应再变化")

    def test_find_next_move_returns_unblocked(self):
        """find_next_move 应返回一个前方无阻挡的箭头。"""
        for lv in LEVELS:
            rows, cols, arrows = load_level(lv.grid)
            move = find_next_move(arrows, rows, cols)
            self.assertIsNotNone(move, f"关卡 {lv.index} 应存在可飞出的箭头")
            self.assertFalse(is_blocked(move, {a.pos for a in arrows},
                                        rows, cols))

    # ---- 星级与计时 ----
    def test_stars_full_when_no_mistakes(self):
        """无失误通关应得 3 星。"""
        g = self._new_game(0)
        self._clear_level(g, 0)
        self.assertEqual(g.state, ui.STATE_CLEAR)
        self.assertEqual(g.clear_stars, 3, "无失误通关应为 3 星")
        self.assertGreaterEqual(g.clear_time, 0, "应记录通关用时")

    def test_stars_reduced_by_mistakes(self):
        """有失误通关，星级应相应降低。"""
        g = self._new_game(1)
        self._click(g, 2, 0)                       # 先制造 1 次失误
        self._settle(g, ui.SHAKE_DURATION + 0.1)
        self._clear_level(g, 1)
        self.assertEqual(g.state, ui.STATE_CLEAR)
        self.assertEqual(g.clear_stars, 2, "1 次失误通关应为 2 星")

    # ---- 关卡解锁 ----
    def test_unlock_progress_after_clear(self):
        """通关后应解锁下一关。"""
        g = self._new_game(0)
        self.assertEqual(g.unlocked, 1)
        self._clear_level(g, 0)
        g._next_level()
        self.assertEqual(g.unlocked, 2, "通关第 1 关后应解锁第 2 关")

    def test_eight_levels_available(self):
        """扩展后应有 8 个关卡且全部可通关。"""
        self.assertEqual(len(LEVELS), 8, "应共有 8 个关卡")


if __name__ == "__main__":
    unittest.main(verbosity=2)
