"""图形界面与交互层（基于 pygame）。

包含：
- 颜色 / 字体等样式常量
- 按钮、箭头绘制等绘制辅助函数
- Game 类：管理游戏状态机（开始 / 游戏中 / 通关 / 失败 / 全部通关），
  处理鼠标点击、飞出/碰撞动画、失误计数与关卡切换。
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

import pygame

from .core import (Arrow, is_blocked, load_level, DIR_NAME,
                   UP, DOWN, LEFT, RIGHT)
from .levels import LEVELS, Level

# ---------------------------------------------------------------------------
# 样式常量
# ---------------------------------------------------------------------------
BG_COLOR = (247, 248, 250)            # 页面背景
BOARD_BG = (255, 255, 255)            # 棋盘背景
GRID_LINE = (226, 230, 236)           # 网格线
TEXT_MAIN = (31, 41, 55)              # 主文字
TEXT_SUB = (107, 114, 128)            # 次要文字
ARROW_COLOR = (47, 107, 255)          # 箭头默认（蓝）
ARROW_FLY = (34, 197, 94)             # 飞出（绿）
ARROW_BLOCKED = (255, 77, 79)         # 碰撞（红）
BUTTON_COLOR = (47, 107, 255)         # 按钮底
BUTTON_HOVER = (64, 128, 255)         # 按钮悬停
BUTTON_TEXT = (255, 255, 255)
PANEL = (255, 255, 255)
SHADOW = (0, 0, 0)

WINDOW_W, WINDOW_H = 800, 640
FPS = 60

FLY_DURATION = 0.45     # 飞出动画时长（秒）
SHAKE_DURATION = 0.5    # 碰撞晃动时长（秒）
FLASH_DURATION = 0.9    # 碰撞提示文字时长（秒）


# ---------------------------------------------------------------------------
# 字体加载（优先使用系统中文字体，避免中文显示为方框）
# ---------------------------------------------------------------------------
_font_cache = {}

# 直接使用系统中文字体文件路径（避免 pygame.font.match_font 在 Windows 上
# 扫描注册表时因某些条目类型异常而崩溃的问题）
_WIN_FONT_DIR = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
_FONT_CANDIDATES = [
    os.path.join(_WIN_FONT_DIR, "msyh.ttc"),     # 微软雅黑
    os.path.join(_WIN_FONT_DIR, "simhei.ttf"),   # 黑体
    os.path.join(_WIN_FONT_DIR, "simsun.ttc"),   # 宋体
    os.path.join(_WIN_FONT_DIR, "Deng.ttf"),     # 等线
]


def get_font(size: int) -> pygame.font.Font:
    if size not in _font_cache:
        font = None
        for path in _FONT_CANDIDATES:
            if os.path.exists(path):
                try:
                    font = pygame.font.Font(path, size)
                    break
                except Exception:
                    continue
        _font_cache[size] = font if font else pygame.font.Font(None, size)
    return _font_cache[size]


# ---------------------------------------------------------------------------
# 绘制辅助函数
# ---------------------------------------------------------------------------
def draw_text(surface, text: str, size: int, color, center=None,
              topleft=None, midleft=None, topright=None) -> pygame.Rect:
    font = get_font(size)
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center is not None:
        rect.center = center
    elif topleft is not None:
        rect.topleft = topleft
    elif midleft is not None:
        rect.midleft = midleft
    elif topright is not None:
        rect.topright = topright
    surface.blit(img, rect)
    return rect


def draw_button(surface, rect: pygame.Rect, text: str, size: int = 26,
                color=BUTTON_COLOR) -> bool:
    """绘制圆角按钮，返回鼠标是否悬停（供调用方改变颜色）。"""
    mouse = pygame.mouse.get_pos()
    hovered = rect.collidepoint(mouse)
    bg = BUTTON_HOVER if hovered else color
    pygame.draw.rect(surface, bg, rect, border_radius=12)
    draw_text(surface, text, size, BUTTON_TEXT, center=rect.center)
    return hovered


def _screen_vector(direction: Tuple[int, int]) -> Tuple[int, int]:
    """把网格方向 (dr, dc) 转为屏幕向量 (dx, dy)。"""
    dr, dc = direction
    return dc, dr


# 方向 -> 字符箭头
ARROW_CHARS = {
    UP: "↑",
    DOWN: "↓",
    LEFT: "←",
    RIGHT: "→",
}


def draw_arrow(surface, cx: int, cy: int, direction, size: int, color):
    """在 (cx, cy) 处绘制一个指向 direction 的字符箭头。"""
    ch = ARROW_CHARS.get(direction, "→")
    font = get_font(int(size * 0.78))
    # 先画一层浅色阴影，增强在浅色背景上的清晰度
    shadow = font.render(ch, True, (255, 255, 255))
    srect = shadow.get_rect(center=(cx + 2, cy + 2))
    surface.blit(shadow, srect)
    img = font.render(ch, True, color)
    rect = img.get_rect(center=(cx, cy))
    surface.blit(img, rect)



# ---------------------------------------------------------------------------
# 动画数据结构
# ---------------------------------------------------------------------------
@dataclass
class FlyAnim:
    arrow: Arrow
    t: float = 0.0


@dataclass
class ShakeAnim:
    arrow: Arrow
    t: float = 0.0


# ---------------------------------------------------------------------------
# 游戏主类
# ---------------------------------------------------------------------------
STATE_START = "start"
STATE_PLAYING = "playing"
STATE_CLEAR = "clear"      # 单关通关
STATE_OVER = "over"        # 失败
STATE_ALL_CLEAR = "all_clear"


class Game:
    def __init__(self, surface: pygame.Surface):
        self.surface = surface
        self.state = STATE_START
        self.level_index = 0          # 当前关卡在 LEVELS 中的下标
        self.level: Level = LEVELS[0]

        # 当前关卡运行数据
        self.rows = 0
        self.cols = 0
        self.arrows: List[Arrow] = []   # 仍在场上的箭头
        self.mistakes = 0               # 剩余失误次数
        self.flying: List[FlyAnim] = []
        self.shaking: List[ShakeAnim] = []
        self.flash_timer = 0.0          # 碰撞提示文字剩余时间

        # 棋盘布局（像素）
        self.cell = 0
        self.board_rect = pygame.Rect(0, 0, 0, 0)

        # 按钮
        self.btn_restart = pygame.Rect(0, 0, 180, 52)
        self.btn_next = pygame.Rect(0, 0, 180, 52)
        self.btn_start = pygame.Rect(0, 0, 200, 60)
        # 开始按钮在开始界面/全部通关界面使用，初始化时即定位（居中）
        self.btn_start.center = (WINDOW_W // 2, 430)

    # ------------------------------------------------------------------
    # 状态切换
    # ------------------------------------------------------------------
    def start_game(self):
        self.level_index = 0
        self.load_level(0)
        self.state = STATE_PLAYING

    def load_level(self, index: int):
        self.level_index = index
        self.level = LEVELS[index]
        self.rows, self.cols, self.arrows = load_level(self.level.grid)
        self.mistakes = self.level.max_mistakes
        self.flying = []
        self.shaking = []
        self.flash_timer = 0.0
        self._compute_layout()

    def restart_level(self):
        self.load_level(self.level_index)
        self.state = STATE_PLAYING

    def _compute_layout(self):
        """根据棋盘行列数计算格子大小与棋盘位置（居中）。"""
        margin_x, margin_y = 40, 150
        top = margin_y
        bottom = WINDOW_H - 100
        avail_w = WINDOW_W - 2 * margin_x
        avail_h = bottom - top
        self.cell = min(avail_w // self.cols, avail_h // self.rows, 110)
        board_w = self.cell * self.cols
        board_h = self.cell * self.rows
        bx = (WINDOW_W - board_w) // 2
        by = top + (avail_h - board_h) // 2
        self.board_rect = pygame.Rect(bx, by, board_w, board_h)

        self.btn_restart.center = (WINDOW_W // 2, WINDOW_H - 52)
        self.btn_next.center = (WINDOW_W // 2, WINDOW_H - 90)
        self.btn_start.center = (WINDOW_W // 2, WINDOW_H - 140)

    # ------------------------------------------------------------------
    # 坐标换算
    # ------------------------------------------------------------------
    def cell_center(self, row: int, col: int) -> Tuple[int, int]:
        x = self.board_rect.x + col * self.cell + self.cell // 2
        y = self.board_rect.y + row * self.cell + self.cell // 2
        return x, y

    def pos_to_cell(self, mx: int, my: int) -> Optional[Tuple[int, int]]:
        if not self.board_rect.collidepoint(mx, my):
            return None
        col = (mx - self.board_rect.x) // self.cell
        row = (my - self.board_rect.y) // self.cell
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return row, col
        return None

    def arrow_at(self, row: int, col: int) -> Optional[Arrow]:
        for a in self.arrows:
            if a.row == row and a.col == col:
                return a
        return None

    def occupied_positions(self) -> Set[Tuple[int, int]]:
        return {a.pos for a in self.arrows}

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.QUIT:
            return "quit"
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self._on_click(event.pos)
        return None

    def _on_click(self, pos: Tuple[int, int]) -> Optional[str]:
        if self.state == STATE_START:
            if self.btn_start.collidepoint(pos):
                self.start_game()
        elif self.state == STATE_PLAYING:
            if self.btn_restart.collidepoint(pos):
                self.restart_level()
                return None
            cell = self.pos_to_cell(*pos)
            if cell is not None:
                self._click_arrow(*cell)
        elif self.state == STATE_CLEAR:
            if self.btn_next.collidepoint(pos):
                self._next_level()
        elif self.state == STATE_OVER:
            if self.btn_restart.collidepoint(pos):
                self.restart_level()
        elif self.state == STATE_ALL_CLEAR:
            if self.btn_start.collidepoint(pos):
                self.start_game()
        return None

    def _click_arrow(self, row: int, col: int):
        arrow = self.arrow_at(row, col)
        if arrow is None:
            return
        # 动画中的箭头不响应点击
        if any(a.arrow == arrow for a in self.shaking):
            return
        if is_blocked(arrow, self.occupied_positions(), self.rows, self.cols):
            # 碰撞：晃动 + 变红 + 扣失误
            self.shaking.append(ShakeAnim(arrow))
            self.flash_timer = FLASH_DURATION
            self.mistakes -= 1
            if self.mistakes <= 0:
                self.mistakes = 0
                self.state = STATE_OVER
        else:
            # 飞出：移出场上集合，进入飞出动画
            self.arrows.remove(arrow)
            self.flying.append(FlyAnim(arrow))

    def _next_level(self):
        if self.level_index + 1 < len(LEVELS):
            self.load_level(self.level_index + 1)
            self.state = STATE_PLAYING
        else:
            self.state = STATE_ALL_CLEAR

    # ------------------------------------------------------------------
    # 逐帧更新
    # ------------------------------------------------------------------
    def update(self, dt: float):
        if self.state != STATE_PLAYING:
            return
        for f in self.flying:
            f.t += dt
        self.flying = [f for f in self.flying if f.t < FLY_DURATION]
        for s in self.shaking:
            s.t += dt
        self.shaking = [s for s in self.shaking if s.t < SHAKE_DURATION]
        if self.flash_timer > 0:
            self.flash_timer -= dt
        # 通关判定：场上已无箭头且飞出动画结束
        if self.state == STATE_PLAYING and not self.arrows and not self.flying:
            self.state = STATE_CLEAR

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def draw(self):
        self.surface.fill(BG_COLOR)
        if self.state == STATE_START:
            self._draw_start()
        elif self.state == STATE_PLAYING:
            self._draw_playing()
        elif self.state == STATE_CLEAR:
            self._draw_clear()
        elif self.state == STATE_OVER:
            self._draw_over()
        elif self.state == STATE_ALL_CLEAR:
            self._draw_all_clear()

    def _draw_start(self):
        draw_text(self.surface, "一箭又一箭", 64, (30, 64, 175),
                  center=(WINDOW_W // 2, 150))
        draw_text(self.surface, "点击箭头，让它们依次飞出棋盘", 26, TEXT_SUB,
                  center=(WINDOW_W // 2, 220))
        self._draw_legend(WINDOW_W // 2, 300)
        draw_button(self.surface, self.btn_start, "开始游戏", size=30)

    def _draw_legend(self, cx: int, cy: int):
        """在开始界面绘制玩法说明图例。"""
        gap = 170   # 列间距需大于最长标签宽度，避免文字重叠
        xs = [cx - gap, cx, cx + gap]
        labels = ["点击箭头", "前方无阻挡 → 飞出", "前方有阻挡 → 扣失误"]
        for i, (x, lab) in enumerate(zip(xs, labels)):
            color = [ARROW_COLOR, ARROW_FLY, ARROW_BLOCKED][i]
            draw_arrow(self.surface, x, cy, (0, 1), 40, color)
            draw_text(self.surface, lab, 16, TEXT_SUB, center=(x, cy + 46))

    def _draw_playing(self):
        # 顶部信息栏
        total = len(LEVELS)
        draw_text(self.surface, f"第 {self.level_index + 1} 关 / 共 {total} 关",
                  28, TEXT_MAIN, topleft=(32, 24))
        draw_text(self.surface, f"剩余箭头：{len(self.arrows)}", 24, TEXT_MAIN,
                  center=(WINDOW_W // 2, 40))
        draw_text(self.surface, f"剩余失误：{self.mistakes}", 24,
                  (255, 77, 79) if self.mistakes <= 1 else TEXT_MAIN,
                  topright=(WINDOW_W - 32, 24))

        # 碰撞提示文字
        if self.flash_timer > 0:
            alpha = int(255 * min(1.0, self.flash_timer / 0.4))
            draw_text(self.surface, "路径被阻挡！", 30, (220, 38, 38),
                      center=(WINDOW_W // 2, 86))

        self._draw_board()
        draw_button(self.surface, self.btn_restart, "重新开始", size=24)

    def _draw_board(self):
        # 棋盘底板
        pygame.draw.rect(self.surface, BOARD_BG, self.board_rect,
                         border_radius=12)
        # 网格线
        for r in range(self.rows + 1):
            y = self.board_rect.y + r * self.cell
            pygame.draw.line(self.surface, GRID_LINE,
                             (self.board_rect.x, y),
                             (self.board_rect.x + self.board_rect.w, y), 2)
        for c in range(self.cols + 1):
            x = self.board_rect.x + c * self.cell
            pygame.draw.line(self.surface, GRID_LINE,
                             (x, self.board_rect.y),
                             (x, self.board_rect.y + self.board_rect.h), 2)
        # 静止箭头
        shaking_set = {s.arrow for s in self.shaking}
        for a in self.arrows:
            cx, cy = self.cell_center(a.row, a.col)
            if a in shaking_set:
                continue  # 晃动中的箭头单独绘制
            draw_arrow(self.surface, cx, cy, a.direction, self.cell,
                       ARROW_COLOR)
        # 晃动中的箭头（变红 + 抖动）
        for s in self.shaking:
            a = s.arrow
            cx, cy = self.cell_center(a.row, a.col)
            offset = math.sin(s.t * 40) * 7
            draw_arrow(self.surface, int(cx + offset), cy, a.direction,
                       self.cell, ARROW_BLOCKED)
        # 飞出中的箭头（变绿 + 沿方向移出 + 淡出）
        for f in self.flying:
            a = f.arrow
            cx, cy = self.cell_center(a.row, a.col)
            sx, sy = _screen_vector(a.direction)
            progress = f.t / FLY_DURATION
            dist = (self.board_rect.w + self.board_rect.h) * progress
            dx, dy = sx * dist, sy * dist
            color = self._fade(ARROW_FLY, 1.0 - progress)
            draw_arrow(self.surface, int(cx + dx), int(cy + dy),
                       a.direction, self.cell, color)

    @staticmethod
    def _fade(color, alpha: float) -> Tuple[int, int, int]:
        return tuple(int(c * alpha) for c in color)

    def _draw_result_panel(self, title: str, subtitle: str, color):
        # 半透明遮罩：雾化背景棋盘，突出结果面板
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((255, 255, 255, 175))
        self.surface.blit(overlay, (0, 0))
        panel = pygame.Rect(0, 0, 460, 320)
        panel.center = (WINDOW_W // 2, WINDOW_H // 2 - 20)
        pygame.draw.rect(self.surface, PANEL, panel, border_radius=18)
        pygame.draw.rect(self.surface, (210, 215, 224), panel, 2,
                         border_radius=18)
        draw_text(self.surface, title, 46, color,
                  center=(panel.centerx, panel.y + 80))
        draw_text(self.surface, subtitle, 24, TEXT_SUB,
                  center=(panel.centerx, panel.y + 150))

    def _draw_clear(self):
        self._draw_board()
        is_last = self.level_index + 1 >= len(LEVELS)
        nxt = "全部通关！" if is_last else "进入下一关"
        self._draw_result_panel("通关！", "太棒了，本关箭头已全部飞出", (34, 197, 94))
        draw_button(self.surface, self.btn_next, nxt, size=26)

    def _draw_over(self):
        self._draw_board()
        self._draw_result_panel("失败", "失误次数已耗尽，再接再厉", (255, 77, 79))
        draw_button(self.surface, self.btn_restart, "重新开始", size=26)

    def _draw_all_clear(self):
        self._draw_result_panel("全部通关", "恭喜！你已通过所有关卡", (30, 64, 175))
        self.btn_start.center = (WINDOW_W // 2, WINDOW_H // 2 + 90)
        draw_button(self.surface, self.btn_start, "再玩一次", size=26)


# ---------------------------------------------------------------------------
# 主循环（供 main.py 调用）
# ---------------------------------------------------------------------------
def run():
    pygame.init()
    pygame.display.set_caption("一箭又一箭")
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    clock = pygame.time.Clock()
    game = Game(screen)
    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        for event in pygame.event.get():
            if game.handle_event(event) == "quit":
                running = False
                break
        game.update(dt)
        game.draw()
        pygame.display.flip()
    pygame.quit()
