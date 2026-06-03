from __future__ import annotations

import sys
from pathlib import Path
import datetime
import json

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from studio_shell.page_shell import page_shell
from studio_shell.shell_ui import inject_style

st.set_page_config(page_title="Experiment Log", page_icon="📝", layout="wide")
inject_style()

WORKSPACE_DIR = Path(PROJECT_ROOT) / "workspace"
LOG_DIR = WORKSPACE_DIR / "experiment_logs"

# 確保紀錄目錄存在
LOG_DIR.mkdir(parents=True, exist_ok=True)

def save_log(title: str, content: str):
    """將實驗紀錄存檔至 workspace"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"log_{timestamp}.json"
    file_path = LOG_DIR / filename
    
    data = {
        "title": title,
        "timestamp": str(datetime.datetime.now()),
        "content": content
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    return file_path

def load_logs() -> list[dict]:
    """讀取所有實驗紀錄"""
    logs = []
    if not LOG_DIR.exists():
        return logs
    
    for file in LOG_DIR.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                logs.append(json.load(f))
        except Exception:
            continue
    return sorted(logs, key=lambda x: x["timestamp"], reverse=True)

def render_main() -> None:
    st.markdown("#### 🧪 實驗紀錄存檔")
    st.info("在這裡記錄你在 Playground 練習的成果，並將它們永久保存在 workspace 中。")

    with st.form("log_form"):
        exp_title = st.text_input("實驗名稱", placeholder="例如：Extra Context 串接測試")
        exp_content = st.text_area("實驗心得/觀察", placeholder="記錄你學到了什麼，或是遇到了什麼問題...", height=150)
        submit_button = st.form_submit_button("💾 提交紀錄")

        if submit_button:
            if exp_title and exp_content:
                saved_path = save_log(exp_title, exp_content)
                st.success(f"✅ 紀錄已成功存檔至：`{saved_path.name}`")
            else:
                st.error("⚠️ 請填寫完整的實驗名稱與心得內容。")

    st.divider()

    st.markdown("#### 📜 歷史紀錄清單")
    logs = load_logs()

    if not logs:
        st.write("目前還沒有任何實驗紀錄。")
    else:
        for log in logs:
            with st.expander(f"📅 {log['timestamp']} - {log['title']}"):
                st.write(log['content'])
                st.caption(f"檔案路徑: `{LOG_DIR}/{log['title']}` (實際檔名包含時間戳)")

def main():
    page_shell(
        "Experiment Log",
        "記錄你的開發歷程，將實驗成果永久保存在 workspace 中。",
        render_main,
        page_name="Experiment Log",
    )

if __name__ == "__main__":
    main()
