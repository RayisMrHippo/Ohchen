#!/usr/bin/env python3
"""Build report/assets/專題海報.png using PIL (no VCR key needed)."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 直式 2:3，2K 解析度
W, H = 1200, 2400

# sage-terracotta 配色
BG = (245, 240, 230)
SAGE = (138, 154, 91)
TERRA = (196, 106, 75)
DARK = (60, 50, 40)
LIGHT = (255, 250, 240)
ACCENT = (180, 140, 100)

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


def draw_title(draw, y):
    draw.rectangle([(0, y), (W, y + 160)], fill=SAGE)
    title = "gootok：你的回覆好幫手"
    f = get_font(48, bold=True)
    bbox = draw.textbbox((0, 0), title, font=f)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, y + 25), title, font=f, fill=(255, 255, 255))
    sub = "組別／組員：個人專題　日期：2026-06-24"
    f2 = get_font(20)
    bbox2 = draw.textbbox((0, 0), sub, font=f2)
    sw = bbox2[2] - bbox2[0]
    draw.text(((W - sw) // 2, y + 100), sub, font=f2, fill=(240, 230, 210))
    return y + 160


def draw_section(draw, y, title, bullets, img_path=None, img_h=0):
    pad = 25
    f_title = get_font(24, bold=True)
    f_body = get_font(16)
    line_h = 28
    title_h = 40
    bullets_h = len(bullets) * line_h + 10
    block_h = title_h + bullets_h + img_h + pad * 2

    draw.rectangle([(pad, y), (W - pad, y + block_h)], fill=LIGHT, outline=ACCENT, width=2)
    draw.text((pad + 15, y + 12), title, font=f_title, fill=TERRA)
    for i, b in enumerate(bullets):
        draw.text((pad + 25, y + title_h + i * line_h), "• " + b, font=f_body, fill=DARK)
    if img_path and img_path.is_file() and img_h > 0:
        try:
            img = Image.open(img_path).convert("RGB")
            max_w = W - pad * 2 - 30
            max_h = img_h - 10
            img.thumbnail((max_w, max_h), Image.LANCZOS)
            ix = (W - img.width) // 2
            iy = y + title_h + bullets_h + 5
            draw.rectangle([(ix - 2, iy - 2), (ix + img.width + 2, iy + img.height + 2)], outline=ACCENT, width=1)
            draw._image.paste(img, (ix, iy))
        except Exception as e:
            print(f"WARN: cannot load {img_path}: {e}", file=sys.stderr)
    return y + block_h + 10


def main():
    report_dir = Path("report")
    assets = report_dir / "assets"

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    y = 0
    y = draw_title(draw, y)

    # 區塊 1：專題介紹
    y = draw_section(draw, y, "1. 專題介紹", [
        "命名靈感：像 TikTok，也有 good talk 的諧音感",
        "一句話：幫使用者快速產生不同風格的回覆句子",
        "主要使用者：遇到黏人的朋友、很煩的朋友，或不好意思拒絕別人的人",
        "解決的問題：不知道怎麼拒絕、怕講得太直接，或想快速回覆時，可產生多種回覆選項",
    ])

    # 區塊 2：Server 拓撲（圖小一點）
    y = draw_section(draw, y, "2. 學校 Server 環境", [
        "透過學校 API Key 呼叫 Ollama Router，由 Router 分配至後端 Ollama 節點執行 LLM",
    ], img_path=assets / "server-topology.png", img_h=200)

    # 區塊 3：系統架構（圖大一點）
    y = draw_section(draw, y, "3. 系統概覽（左欄 ↔ 右欄 Agent）", [
        "左欄自訂頁：個人小卡片、他人小卡片、對話內容＋回覆方式／長度、分享功能",
        "左欄 → Agent：自己的資料、對方資料、聊天內容、回覆語氣整理後送出",
        "Agent → 左欄：產生多個回覆選項，顯示回左欄",
        "完整例子：填好小卡片 → 按生成按鈕 → Agent 產生 5 種回覆 → 選一個複製或傳到 Discord",
    ], img_path=assets / "project-architecture.png", img_h=280)

    # 區塊 4：成果
    y = draw_section(draw, y, "4. 成果", [
        "根據情境與語氣產生多種可選的回覆句",
        "一次提供多個選項，讓使用者挑到滿意為止",
        "回覆可直接複製",
        "回覆可轉發分享",
        "可直接傳送到 Discord 頻道",
    ])

    # 區塊 5：創新
    y = draw_section(draw, y, "5. 創新／亮點", [
        "不只是聊天，而是把「自己是誰、對方是誰、想用什麼語氣」一起納入回覆生成",
        "貼近真實人際互動，特別是「不好意思拒絕別人」的情境",
        "提供多種語氣與長度選擇，像挑選句子一樣挑出最適合的回覆",
        "Discord 傳送功能讓 App 不只停留在產生文字，也能接到實際社群平台",
    ])

    # 區塊 6：技術含量
    y = draw_section(draw, y, "6. 技術含量", [
        "Agent Studio + Streamlit 製作左欄互動介面",
        "本機 JSON 儲存個人小卡片、他人小卡片、回覆設定、Discord Webhook 設定",
        "Agent 依據左欄整理出的情境資料產生回覆",
        "Discord Webhook 將選定回覆傳送到 Discord 頻道",
        "嘗試設計自動讀取 Discord 訊息的收件匣功能（需 Bot 權限，目前屬進階功能）",
    ])

    # 底部
    f_foot = get_font(14)
    draw.text((30, H - 40), "gootok · Agent Studio 專題報告 · 2026-06-24", font=f_foot, fill=ACCENT)

    out = assets / "專題海報.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    print(f"OK: {out} ({W}x{H})")


if __name__ == "__main__":
    main()