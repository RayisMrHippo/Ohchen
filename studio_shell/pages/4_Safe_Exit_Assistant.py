from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from studio_shell.page_shell import page_shell
from studio_shell.shell_ui import format_extra_context, inject_style


st.set_page_config(page_title="安全離開助手", page_icon="🧭", layout="wide")
inject_style()


LOCATIONS = {
    "教室": {
        "廁所": "從靠走廊的位置離開，先到門口，再沿走廊走到最近的廁所。",
        "辦公室": "離開教室後直接往老師辦公室方向走，需要時請老師陪你處理。",
        "操場": "從教室走到樓梯或出口，往空曠的操場移動，保持在人多可見的位置。",
    },
    "走廊": {
        "教室": "直接回到最近的教室，坐到靠近同學或老師的位置。",
        "辦公室": "沿著走廊往辦公室方向走，途中不要停下來爭辯。",
        "廁所": "走到最近的廁所或洗手台區域，先讓自己有一點距離。",
    },
    "操場": {
        "教室": "沿原路回教室，選人多且明亮的路線。",
        "辦公室": "往校舍入口移動，再前往辦公室找可信任的大人。",
        "福利社": "往人多的福利社移動，先避開一對一相處。",
    },
    "福利社": {
        "教室": "買完或假裝想起有事，直接回教室。",
        "辦公室": "從福利社往辦公室移動，必要時請店員或同學陪你走。",
        "廁所": "往最近的廁所或洗手台移動，先中斷對話。",
    },
}

EXIT_LINES = {
    "溫和": "我現在想自己待一下，等等再聊。",
    "明確": "我現在不想聊天，我要先離開。",
    "求助": "我需要一點協助，可以陪我去找老師嗎？",
}

FRIEND_MESSAGES = {
    "低調提醒": "我想先離開一下。如果你也覺得不舒服，可以跟我一起往{destination}走。",
    "請朋友會合": "我現在要去{destination}，你方便過來跟我會合嗎？",
    "請朋友求助": "我現在有點不安，準備去{destination}。如果我沒有回覆，請幫我找老師或可信任的大人。",
}


def _route_for(current_place: str, destination: str) -> str:
    return LOCATIONS.get(current_place, {}).get(
        destination,
        f"從「{current_place}」往「{destination}」移動，優先選人多、明亮、靠近老師或工作人員的路線。",
    )


def render_main() -> str:
    st.markdown("#### 安全離開助手")
    st.info(
        "這個工具不辨識或標記特定的人。"
        "當你覺得需要空間時，可以手動啟動，快速得到離開路線和一句好用的離開台詞。"
    )

    col1, col2 = st.columns(2)
    with col1:
        current_place = st.selectbox("我現在在哪裡？", list(LOCATIONS.keys()), key="safe_exit_current")
        urgency = st.radio("我現在需要多快離開？", ["普通", "盡快", "需要找人幫忙"], horizontal=True, key="safe_exit_urgency")
    with col2:
        destination = st.selectbox("我想去哪裡？", ["教室", "廁所", "辦公室", "操場", "福利社"], index=2, key="safe_exit_destination")
        line_style = st.radio("離開台詞風格", list(EXIT_LINES.keys()), horizontal=True, key="safe_exit_line_style")

    st.divider()
    st.markdown("#### 通知朋友")
    notify_friend = st.checkbox("提醒我傳訊息給朋友", value=True, key="safe_exit_notify_friend")
    friend_col, message_col = st.columns(2)
    with friend_col:
        friend_name = st.text_input("朋友稱呼", placeholder="例如：阿明", key="safe_exit_friend_name")
    with message_col:
        message_style = st.selectbox("訊息類型", list(FRIEND_MESSAGES.keys()), key="safe_exit_message_style")

    st.divider()
    st.markdown("#### 立即方案")
    route = _route_for(current_place, destination)
    exit_line = EXIT_LINES[line_style]

    if urgency == "需要找人幫忙":
        st.error("先往老師、櫃台、店員或人多的地方移動，並請可信任的人陪你。")
    elif urgency == "盡快":
        st.warning("先離開現場，不需要解釋太多。保持在人多、明亮、可被看見的位置。")
    else:
        st.success("先穩住節奏，用簡短台詞離開現場。")

    route_col, line_col = st.columns(2)
    with route_col:
        st.markdown("##### 建議路線")
        st.write(route)
    with line_col:
        st.markdown("##### 可以直接說")
        st.code(exit_line, language="text")

    friend_message = ""
    if notify_friend:
        friend_message = FRIEND_MESSAGES[message_style].format(destination=destination)
        if friend_name:
            friend_message = f"{friend_name}，{friend_message}"

        st.markdown("##### 傳給朋友的訊息草稿")
        st.code(friend_message, language="text")
        st.caption("這裡只產生訊息草稿，不會自動傳送。請你確認內容後再傳給朋友。")

    st.divider()
    st.markdown("#### 給 Agent 的摘要")
    extra = format_extra_context(
        "安全離開助手",
        目前位置=current_place,
        想去地點=destination,
        狀況強度=urgency,
        建議路線=route,
        離開台詞=exit_line,
        朋友提醒="需要" if notify_friend else "不需要",
        給朋友的訊息=friend_message or "（未啟用）",
    )
    st.code(extra, language="text")

    st.markdown("#### 右欄可以這樣問")
    st.markdown(
        """
- 「幫我把離開台詞改得更自然一點。」
- 「根據我的位置，給我三個不尷尬離開的說法。」
- 「如果對方一直追問，我可以怎麼回？」
"""
    )

    return extra


page_shell(
    "安全離開助手",
    "需要空間時，快速整理離開路線、求助方向與可直接使用的台詞。",
    render_main,
    page_name="安全離開助手",
)
