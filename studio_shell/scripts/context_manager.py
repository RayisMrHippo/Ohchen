import streamlit as st

def get_extra_context():
    """
    從 session_state 中提取左側欄位的資訊，並格式化為文字。
    假設左側欄位的元件名稱與 session_state 的 key 對應。
    """
    # 預設值，防止 key 不存在時報錯
    nickname = st.session_state.get('nickname', '未設定')
    mood = st.session_state.get('mood', '平靜')
    energy = st.session_state.get('energy', 50)
    events = st.session_state.get('today_events', '無')
    counter = st.session_state.get('counter', 0)

    # 格式化為結構化的 Extra Context
    context_str = f"""
### [Extra Context: User Status]
- **Nickname**: {nickname}
- **Current Mood**: {mood}
- **Energy Level**: {energy}/100
- **Today's Events**: {events}
- **Counter Value**: {counter}
---
"""
    return context_str

if __name__ == "__main__":
    # 測試用：模擬 session_state
    st.session_state['nickname'] = "小明"
    st.session_state['mood'] = "興奮"
    st.session_state['energy'] = 85
    st.session_state['today_events'] = "完成了 Agent 串接實驗"
    st.session_state['counter'] = 5
    
    st.write("Testing Context Generation...")
    st.write(get_extra_context())
