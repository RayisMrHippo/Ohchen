#!/usr/bin/env python3
"""重畫 report/assets/project-architecture.png（用 PIL，避開 mmdc 字型問題）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1400, 900

# 配色（與海報一致）
BG = (245, 240, 230)
LEFT_BG = (220, 232, 215)      # 左欄淺綠
RIGHT_BG = (245, 220, 200)     # 右欄淺橘
STORE_BG = (230, 225, 210)     # 資料存放淺米
NODE_BG = (255, 250, 240)
NODE_BORDER = (138, 154, 91)
ARROW = (80, 70, 60)
TEXT = (60, 50, 40)

FONT_TITLE = "C:\\Windows\\Fonts\\msyhbd.ttc"
FONT_BODY = "C:\\Windows\\Fonts\\msyh.ttc"
FONT_FALLBACK = "C:\\Windows\\Fonts\\arial.ttf"


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in [FONT_TITLE if bold else FONT_BODY, FONT_FALLBACK]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_node(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, text: str, font_size: int = 18) -> tuple[int, int, int, int]:
    """畫節點框，回傳 (x1, y1, x2, y2)"""
    draw.rounded_rectangle([(x, y), (x + w, y + h)], radius=10, fill=NODE_BG, outline=NODE_BORDER, width=2)
    f = get_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((x + (w - tw) // 2, y + (h - th) // 2 - 2), text, font=f, fill=TEXT)
    return (x, y, x + w, y + h)


def draw_arrow(draw: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int, label: str = "") -> None:
    """畫箭頭 + 標籤"""
    draw.line([(x1, y1), (x2, y2)], fill=ARROW, width=2)
    # 箭頭頭
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    ah = 10
    ax1 = x2 - ah * math.cos(angle - 0.4)
    ay1 = y2 - ah * math.sin(angle - 0.4)
    ax2 = x2 - ah * math.cos(angle + 0.4)
    ay2 = y2 - ah * math.sin(angle + 0.4)
    draw.polygon([(x2, y2), (ax1, ay1), (ax2, ay2)], fill=ARROW)
    # 標籤
    if label:
        f = get_font(14)
        bbox = draw.textbbox((0, 0), label, font=f)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        mx = (x1 + x2) // 2 - lw // 2
        my = (y1 + y2) // 2 - lh // 2 - 8
        # 白底
        draw.rectangle([(mx - 4, my - 2), (mx + lw + 4, my + lh + 2)], fill=BG)
        draw.text((mx, my), label, font=f, fill=TEXT)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.ImageDraw = ImageDraw.Draw(img)

    # 三個子圖區塊
    # 左欄
    draw.rounded_rectangle([(40, 80), (520, 820)], radius=15, fill=LEFT_BG, outline=NODE_BORDER, width=2)
    draw.text((180, 50), "左欄網頁", font=get_font(22, bold=True), fill=TEXT)

    # 右欄
    draw.rounded_rectangle([(560, 80), (920, 820)], radius=15, fill=RIGHT_BG, outline=NODE_BORDER, width=2)
    draw.text((680, 50), "右欄 AI 助手", font=get_font(22, bold=True), fill=TEXT)

    # 資料存放
    draw.rounded_rectangle([(960, 80), (1360, 820)], radius=15, fill=STORE_BG, outline=NODE_BORDER, width=2)
    draw.text((1090, 50), "資料存放", font=get_font(22, bold=True), fill=TEXT)

    # 左欄節點
    n1 = draw_node(draw, 80, 130, 400, 60, "我的個人小卡片")
    n2 = draw_node(draw, 80, 220, 400, 60, "對方小卡片")
    n3 = draw_node(draw, 80, 310, 400, 60, "對話情境與想要語氣")
    n4 = draw_node(draw, 80, 400, 400, 60, "五種回覆選項")
    n5 = draw_node(draw, 80, 490, 400, 60, "複製、分享、傳到 Discord")
    n6 = draw_node(draw, 80, 580, 400, 60, "整理成 Agent 摘要")

    # 右欄節點
    n7 = draw_node(draw, 600, 200, 280, 60, "聊天面板")
    n8 = draw_node(draw, 600, 320, 280, 60, "AI 回覆大腦")

    # 資料存放節點
    n9 = draw_node(draw, 1000, 130, 320, 60, "小卡片與設定檔")
    n10 = draw_node(draw, 1000, 220, 320, 60, "Discord 收件匣")
    n11 = draw_node(draw, 1000, 310, 320, 60, "Discord 頻道")

    # 箭頭
    # 左欄內部
    draw_arrow(draw, 280, 190, 280, 220, "")  # 我的 → 對方
    draw_arrow(draw, 280, 280, 280, 310, "")  # 對方 → 對話
    draw_arrow(draw, 280, 370, 280, 400, "")  # 對話 → 五種
    draw_arrow(draw, 280, 460, 280, 490, "")  # 五種 → 分享
    draw_arrow(draw, 280, 550, 280, 580, "")  # 分享 → 摘要

    # 摘要 → 聊天面板
    draw_arrow(draw, 480, 610, 600, 230, "每則問題附上左欄情境")

    # 聊天面板 → AI 大腦
    draw_arrow(draw, 740, 260, 740, 320, "")

    # AI 大腦 → 五種回覆
    draw_arrow(draw, 600, 350, 480, 430, "依照人物關係與語氣產生回覆")

    # 分享 → Discord 頻道
    draw_arrow(draw, 480, 520, 1000, 340, "使用者確認後送出")

    # 個人 → 設定檔
    draw_arrow(draw, 480, 160, 1000, 160, "儲存個人設定")
    # 對方 → 設定檔
    draw_arrow(draw, 480, 250, 1000, 160, "儲存對方資料")
    # 設定檔 → 個人
    draw_arrow(draw, 1000, 160, 480, 160, "重新打開頁面時讀取")
    # Discord 收件匣 → 對話情境
    draw_arrow(draw, 1000, 250, 480, 340, "進階功能：帶入別人訊息")

    # 標題
    draw.text((40, 15), "gootok 專案架構圖", font=get_font(20, bold=True), fill=TEXT)

    out = Path("report/assets/project-architecture.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    print(f"OK: {out} ({W}x{H})")


if __name__ == "__main__":
    main()