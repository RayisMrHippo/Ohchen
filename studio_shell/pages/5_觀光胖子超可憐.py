from __future__ import annotations

import html
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHELL_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from studio_shell.page_shell import page_shell
from studio_shell.shell_ui import (
    format_extra_context,
    inject_style,
    load_page_data,
    save_page_data,
    shared_data_path,
)

PAGE_NAME = "觀光胖子超可憐"

st.set_page_config(page_title=PAGE_NAME, page_icon="💬", layout="wide")
inject_style()

TONE_OPTIONS = [
    "敷衍一下",
    "婉拒版",
    "好朋友怕尷尬版",
    "打嘴砲版",
    "直接拒絕",
    "不爽但先忍",
    "有界線但不想吵",
    "偏兇一點",
    "罵髒話版",
    "拿理由推掉",
]

LENGTH_OPTIONS = ["超短版", "正常版", "帶理由版"]

REFRESH_TONE_ORDER = [
    "婉拒版",
    "直接拒絕",
    "有界線但不想吵",
    "拿理由推掉",
    "敷衍一下",
    "好朋友怕尷尬版",
    "不爽但先忍",
    "打嘴砲版",
    "偏兇一點",
    "罵髒話版",
]



def build_style_hint(my_profile: dict[str, str]) -> dict[str, str]:
    return {
        "my_tone": (my_profile.get("my_tone") or "").strip(),
        "my_personality": (my_profile.get("my_personality") or "").strip(),
        "my_habit": (my_profile.get("my_habit") or "").strip(),
        "my_note": (my_profile.get("my_note") or "").strip(),
    }



def dedupe_keep_order(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        cleaned = " ".join(line.strip().split())
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result



def rotated_tone(base_tone: str, refresh_count: int) -> str:
    if refresh_count <= 0:
        return base_tone

    tones = [base_tone] + [tone for tone in REFRESH_TONE_ORDER if tone != base_tone]
    return tones[refresh_count % len(tones)]



def pick_five_different(lines: list[str], rejected_replies: list[str], refresh_count: int) -> list[str]:
    rejected = set(rejected_replies)
    candidates = [line for line in dedupe_keep_order(lines) if line not in rejected]
    if not candidates:
        candidates = dedupe_keep_order(lines)

    if not candidates:
        return []

    offset = (refresh_count * 2) % len(candidates)
    rotated = candidates[offset:] + candidates[:offset]
    return rotated[:5]



def render_reply_actions(reply: str, idx: int) -> None:
    js_reply = json.dumps(reply, ensure_ascii=False)
    line_url = "https://line.me/R/share?text=" + urllib.parse.quote(reply)
    safe_line_url = html.escape(line_url, quote=True)

    components.html(
        f"""
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin:-4px 0 18px;">
          <button id="copy-{idx}" style="border:1px solid #d0d7de; border-radius:8px; background:#fff; padding:8px 12px; cursor:pointer;">
            複製
          </button>
          <button id="share-{idx}" style="border:1px solid #d0d7de; border-radius:8px; background:#fff; padding:8px 12px; cursor:pointer;">
            手機分享
          </button>
          <a href="{safe_line_url}" target="_blank" rel="noopener noreferrer"
             style="border:1px solid #06c755; border-radius:8px; color:#06c755; background:#fff; padding:8px 12px; text-decoration:none; font:14px sans-serif;">
            LINE
          </a>
          <span id="status-{idx}" style="align-self:center; color:#57606a; font:13px sans-serif;"></span>
        </div>
        <script>
        const reply{idx} = {js_reply};
        const status{idx} = document.getElementById("status-{idx}");
        document.getElementById("copy-{idx}").onclick = async () => {{
          try {{
            await navigator.clipboard.writeText(reply{idx});
            status{idx}.textContent = "已複製";
          }} catch (error) {{
            status{idx}.textContent = "請長按上方文字複製";
          }}
        }};
        document.getElementById("share-{idx}").onclick = async () => {{
          if (navigator.share) {{
            try {{
              await navigator.share({{ text: reply{idx} }});
              status{idx}.textContent = "已開啟分享";
            }} catch (error) {{
              status{idx}.textContent = "";
            }}
          }} else {{
            try {{
              await navigator.clipboard.writeText(reply{idx});
              status{idx}.textContent = "此裝置不支援分享，已先複製";
            }} catch (error) {{
              status{idx}.textContent = "此裝置不支援分享";
            }}
          }}
        }};
        </script>
        """,
        height=58,
    )



def is_discord_webhook_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url.strip())
    return (
        parsed.scheme == "https"
        and parsed.netloc in {"discord.com", "discordapp.com"}
        and parsed.path.startswith("/api/webhooks/")
    )



def send_to_discord_webhook(webhook_url: str, reply: str, username: str) -> tuple[bool, str]:
    webhook_url = webhook_url.strip()
    if not is_discord_webhook_url(webhook_url):
        return False, "Discord Webhook URL 格式不對。"

    payload = {
        "content": reply[:2000],
        "username": username.strip() or "Reply Helper",
        "allowed_mentions": {"parse": []},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "AgentStudioReplyHelper/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if 200 <= response.status < 300:
                return True, "已送到 Discord。"
            return False, f"Discord 回傳狀態碼：{response.status}"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        detail = body[:180] if body else str(exc)
        return False, f"Discord 傳送失敗：{detail}"
    except urllib.error.URLError as exc:
        return False, f"連線到 Discord 失敗：{exc.reason}"
    except TimeoutError:
        return False, "連線到 Discord 逾時。"



def is_close_friend(person: dict[str, str]) -> bool:
    relationship = (person.get("relationship") or "").strip()
    importance_to_me = (person.get("importance_to_me") or "").strip()
    note = (person.get("note") or "").strip()
    return (
        "好朋友" in relationship
        or "很熟" in relationship
        or importance_to_me == "高"
        or "一起" in note
    )



def generate_replies(
    my_profile: dict[str, str],
    person: dict[str, str],
    request_text: str,
    tone: str,
    chat_context: str,
    length_mode: str,
    rejected_replies: list[str] | None = None,
    refresh_count: int = 0,
) -> list[str]:
    relationship = (person.get("relationship") or "").strip()
    importance_to_me = (person.get("importance_to_me") or "").strip()
    request_text = request_text.strip()
    chat_context = chat_context.strip()
    style = build_style_hint(my_profile)
    close_friend = is_close_friend(person)

    if not request_text:
        return []

    my_tone = style["my_tone"]
    my_habit = style["my_habit"]
    my_note = style["my_note"]

    sweary = any(word in my_tone + my_habit for word in ["幹", "靠杯", "靠邀", "機掰", "他媽", "媽的"])
    likes_short = any(word in my_habit + my_tone for word in ["短", "簡短", "不會打太多字"])
    casual = any(word in my_tone for word in ["直接", "白話", "愛笑"])

    short_reason_lines = [
        "今天不行 我有事",
        "我等等有事",
        "我要跟別人走",
        "我等一下要去找老師",
        "我先去廁所",
    ]

    normal_reason_lines = [
        "今天不行 我等等有事",
        "我這次不去 我已經有安排了",
        "我等等要跟別人走 先不陪",
        "我現在沒空 晚點也不一定行",
        "我今天真的不想出門",
    ]

    long_reason_lines = [
        "今天不行 我已經有安排了 你找別人比較快",
        "我這次真的不想去 而且我等等有事",
        "我先不去 我今天想自己待著",
        "我等等要跟別人走 所以這次不行",
        "我今天沒空 你不用等我了",
    ]

    tone_map = {
        "敷衍一下": {
            "超短版": ["今天先不要欸", "我這次不行", "先不要啦", "我今天沒空", "改天再說"],
            "正常版": ["今天先不要欸 我這次沒空", "我這次不行 改天再說", "先不要啦 我今天有事", "我今天真的不行", "我今天先 pass"],
            "帶理由版": ["今天先不要欸 我等等有事", "我這次不行 我要跟別人走", "先不要啦 我今天真的沒空", "改天再說 我今天有安排", "我今天先 pass 我等等要忙"],
        },
        "婉拒版": {
            "超短版": ["我先不要欸", "這次先不行", "我今天不太方便", "我先 pass", "改天再約"],
            "正常版": ["我先不要欸 我今天不太方便", "這次先不行 改天再約", "我今天不太方便 先 pass", "我這次先不去了 抱歉", "改天再約 我今天真的不行"],
            "帶理由版": ["我先不要欸 我今天有點忙", "這次先不行 我等等有事", "我今天不太方便 改天再約", "我這次先不去了 我今天有安排", "改天再約 我今天真的不行"],
        },
        "好朋友怕尷尬版": {
            "超短版": ["我這次先不要啦", "今天先不行欸", "我有點尷尬哈哈", "我先 pass 一下", "改天再陪你"],
            "正常版": ["我這次先不要啦 有點不好意思", "今天先不行欸 改天再陪你", "我有點尷尬哈哈 這次先 pass", "我這次先不去啦 不要介意", "改天再約 我這次真的不行"],
            "帶理由版": ["我這次先不要啦 我等等要補習", "今天先不行欸 我時間真的對不上", "我有點不好意思 但我這次真的沒辦法", "我這次先不去啦 我今天有安排", "改天再約 我這次時間真的不能配"],
        },
        "打嘴砲版": {
            "超短版": ["不要鬧 我才不要", "你自己去啦笑死", "先不要 我又不是你女友", "改天啦 白痴", "今天不行啦 笑你"],
            "正常版": ["不要鬧 我才不要陪你去", "你自己去啦笑死 我這次不行", "先不要 我又不是隨 call 隨到", "改天啦 白痴 我這次沒空", "今天不行啦 不然你跪下來求我"],
            "帶理由版": ["不要鬧 我等等要補習 哪有空陪你", "你自己去啦笑死 我時間根本對不上", "先不要 我又不是隨 call 隨到 我今天有事", "改天啦 白痴 我這次真的沒空", "今天不行啦 我要補習 你找別人"],
        },
        "直接拒絕": {
            "超短版": ["我不要", "我不想去", "這次不要", "我先不陪", "我沒要去"],
            "正常版": ["我不要 我今天不想去", "我不想去 你找別人", "這次不要 我沒那個心情", "我先不陪 你自己去", "我沒要去 先這樣"],
            "帶理由版": ["我不要 我今天有事", "我不想去 而且我等等沒空", "這次不要 我要跟別人走", "我先不陪 我今天有安排", "我沒要去 你找別人比較快"],
        },
        "不爽但先忍": {
            "超短版": ["我就說我不要了", "不要一直找我啦", "我今天真的沒力", "先不要煩我", "我現在不想"],
            "正常版": ["我就說我不要了 不要再問", "不要一直找我啦 我今天真的沒力", "我今天真的沒力 先不要", "先不要煩我 我現在不想", "我現在不想 真的"],
            "帶理由版": ["我就說我不要了 我等等有事", "不要一直找我啦 我今天真的很累", "我今天真的沒力 而且我等等要先走", "先不要煩我 我現在沒空", "我現在不想 我今天有安排"],
        },
        "有界線但不想吵": {
            "超短版": ["我今天想自己待著", "這次先讓我拒絕", "我現在不要", "你找別人比較快", "我不想答應這個"],
            "正常版": ["我今天想自己待著 先不要", "這次先讓我拒絕 我不太想去", "我現在不要 你找別人吧", "你找別人比較快 我今天不行", "我不想答應這個 先這樣"],
            "帶理由版": ["我今天想自己待著 我等等也有事", "這次先讓我拒絕 我今天不太方便", "我現在不要 我等等要跟別人走", "你找別人比較快 我今天有安排", "我不想答應這個 我今天真的沒空"],
        },
        "偏兇一點": {
            "超短版": ["我就不要", "你自己去", "不要再盧了", "我沒空理這個", "你找別人"],
            "正常版": ["我就不要 不要再問了", "你自己去 我沒差", "不要再盧了 很煩", "我沒空理這個 先這樣", "你找別人 我不去"],
            "帶理由版": ["我就不要 我今天有事", "你自己去 我等等沒空", "不要再盧了 我今天很忙", "我沒空理這個 我等等要走", "你找別人 我今天不去"],
        },
        "罵髒話版": {
            "超短版": ["幹 我不要", "靠 我不想去", "媽的 這次不要", "靠北 你找別人", "幹 不要再問"],
            "正常版": ["幹 我不要 我今天不想去", "靠 我真的不想 你找別人", "媽的 這次不要 不要再問了", "靠北 我先不陪 你自己去", "幹 我沒要去 先這樣"],
            "帶理由版": ["幹 我不要 我今天有事", "靠 我真的不想 而且我等等沒空", "媽的 這次不要 我要跟別人走", "靠北 我先不陪 我今天有安排", "幹 我沒要去 你找別人比較快"],
        },
        "拿理由推掉": {
            "超短版": short_reason_lines,
            "正常版": normal_reason_lines,
            "帶理由版": long_reason_lines,
        },
    }

    effective_tone = rotated_tone(tone, refresh_count)
    lines = list(tone_map.get(effective_tone, tone_map["直接拒絕"]).get(length_mode, []))

    if close_friend and effective_tone in {"婉拒版", "好朋友怕尷尬版"}:
        if length_mode == "超短版":
            lines += ["改天我補你", "下次再一起"]
        elif length_mode == "正常版":
            lines += ["改天我補陪你", "下次再一起 我這次真的不行"]
        else:
            lines += ["改天我補你 這次真的時間對不上", "下次再一起 我這次真的沒辦法"]

    if close_friend and effective_tone == "打嘴砲版":
        if length_mode == "超短版":
            lines += ["下次再嘴你", "改天再陪你鬧"]
        elif length_mode == "正常版":
            lines += ["改天再陪你鬧 我這次不行", "下次再給你約到啦"]
        else:
            lines += ["改天再陪你鬧 我這次真的時間不行", "下次再給你約到 今天先算了"]

    if chat_context and length_mode != "超短版":
        lines += [
            "我剛剛就說今天不行了",
            "我不是已經說沒空了嗎",
        ]

    if importance_to_me == "高" and effective_tone in {"敷衍一下", "婉拒版", "好朋友怕尷尬版", "有界線但不想吵"} and length_mode != "超短版":
        lines += [
            "不是在兇你 但我真的不想",
            "我只是這次真的不想去",
        ]

    if relationship and effective_tone == "拿理由推掉" and length_mode == "帶理由版":
        lines += [
            "我真的有事 先不陪了",
            "今天先放過我",
        ]

    if casual and length_mode != "帶理由版":
        lines += [
            "我今天真的沒fu",
            "今天真的沒想跟人出去",
        ]

    if sweary and effective_tone in {"不爽但先忍", "偏兇一點", "罵髒話版"}:
        if length_mode == "超短版":
            lines += ["幹 我不要", "靠 不要再問"]
        else:
            lines += ["幹 我今天真的不想", "靠 我就說不要了"]

    if my_note and "理由" in my_note and effective_tone != "拿理由推掉" and length_mode == "帶理由版":
        lines += [
            "我等等真的有事",
            "我等一下要先閃",
        ]

    if request_text and length_mode == "帶理由版" and effective_tone in {"直接拒絕", "有界線但不想吵", "好朋友怕尷尬版"}:
        lines += [
            "這個我先不要 我今天不想",
            "那個我真的不想答應",
        ]

    if likes_short:
        lines = [line.replace("我現在沒有要去", "我現在不要") for line in lines]

    if refresh_count > 0:
        lines += [
            "算了我這次真的不要 你不用等我",
            "我換個說法 我今天就是不想去",
            "這個我不接 你找別人比較快",
            "我今天先收掉 不想再討論這個",
            "我不要把話講太重 但答案是不行",
            "今天不約 我想把時間留給自己",
            "我這次不跟 你自己安排就好",
            "我已經決定不去了 不用再問我",
        ]

    return pick_five_different(lines, rejected_replies or [], refresh_count)



def render_main() -> str:
    state = load_page_data(PAGE_NAME, shell_root=SHELL_ROOT)

    my_profile = state.get("my_profile", {})
    if not isinstance(my_profile, dict):
        my_profile = {}

    people = state.get("people", [])
    if not isinstance(people, list):
        people = []

    selected_person_name = state.get("selected_person_name", "")
    request_text = state.get("request_text", "")
    tone_default = state.get("tone", TONE_OPTIONS[0])
    length_mode = state.get("length_mode", LENGTH_OPTIONS[0])
    chat_context = state.get("chat_context", "")
    generated_replies = state.get("generated_replies", [])
    if not isinstance(generated_replies, list):
        generated_replies = []
    rejected_replies = state.get("rejected_replies", [])
    if not isinstance(rejected_replies, list):
        rejected_replies = []
    refresh_count = state.get("refresh_count", 0)
    if not isinstance(refresh_count, int):
        refresh_count = 0
    discord_webhook_url = state.get("discord_webhook_url", "")
    if not isinstance(discord_webhook_url, str):
        discord_webhook_url = ""
    discord_username = state.get("discord_username", "Reply Helper")
    if not isinstance(discord_username, str):
        discord_username = "Reply Helper"
    remember_discord_webhook = state.get("remember_discord_webhook", False) is True
    if "tourist_discord_webhook_url" not in st.session_state:
        st.session_state.tourist_discord_webhook_url = discord_webhook_url

    if tone_default not in TONE_OPTIONS:
        tone_default = TONE_OPTIONS[0]
    if length_mode not in LENGTH_OPTIONS:
        length_mode = LENGTH_OPTIONS[0]

    st.markdown("#### 人物設定 + 回覆生成器")
    st.caption("現在可以切換超短版、正常版、帶理由版，讓回覆更接近你當下想回的長度。")

    with st.expander("我的小卡片", expanded=True):
        my_tone = st.text_input(
            "我的講話口氣",
            value=my_profile.get("my_tone", ""),
            placeholder="例如：偏直接、會嘴一下、很白話、偶爾髒話",
        )
        my_personality = st.text_input(
            "我的個性",
            value=my_profile.get("my_personality", ""),
            placeholder="例如：怕尷尬但也懶得配合、容易不耐煩",
        )
        my_habit = st.text_input(
            "我的說話習慣",
            value=my_profile.get("my_habit", ""),
            placeholder="例如：很少打長句、常講沒空/今天不行/我先閃",
        )
        my_note = st.text_area(
            "其他補充",
            value=my_profile.get("my_note", ""),
            placeholder="例如：希望回覆順便帶理由，但不要太假",
            height=90,
        )
        my_profile = {
            "my_tone": my_tone,
            "my_personality": my_personality,
            "my_habit": my_habit,
            "my_note": my_note,
        }

    with st.expander("新增人物", expanded=False):
        new_name = st.text_input("名字", placeholder="例如：阿哲", key="tourist_new_name")
        new_personality = st.text_input("個性", placeholder="例如：很黏、愛盧人、情緒很多", key="tourist_new_personality")
        new_relationship = st.text_input("你和他的關係", placeholder="例如：同學、朋友、前室友、好朋友", key="tourist_new_relationship")

        col1, col2 = st.columns(2)
        with col1:
            new_importance_to_me = st.selectbox("他對你的重要性", ["低", "中", "高"], index=1, key="tourist_importance_to_me")
        with col2:
            new_importance_to_them = st.selectbox("你對他的重要性", ["低", "中", "高"], index=1, key="tourist_importance_to_them")

        new_note = st.text_area(
            "補充描述",
            placeholder="例如：很愛盧、很常裝可憐、講話會一直黏著你，或其實是很好的朋友",
            height=100,
            key="tourist_new_note",
        )

        if st.button("新增人物", use_container_width=True):
            if new_name.strip():
                updated_people = [p for p in people if p.get("name") != new_name.strip()]
                updated_people.append(
                    {
                        "name": new_name.strip(),
                        "personality": new_personality.strip(),
                        "relationship": new_relationship.strip(),
                        "importance_to_me": new_importance_to_me,
                        "importance_to_them": new_importance_to_them,
                        "note": new_note.strip(),
                    }
                )
                people = updated_people
                selected_person_name = new_name.strip()
                save_page_data(
                    PAGE_NAME,
                    {
                        "my_profile": my_profile,
                        "people": people,
                        "selected_person_name": selected_person_name,
                        "request_text": request_text,
                        "tone": tone_default,
                        "length_mode": length_mode,
                        "chat_context": chat_context,
                        "generated_replies": generated_replies,
                        "rejected_replies": rejected_replies,
                        "refresh_count": refresh_count,
                        "discord_webhook_url": discord_webhook_url if remember_discord_webhook else "",
                        "discord_username": discord_username,
                        "remember_discord_webhook": remember_discord_webhook,
                    },
                    shell_root=SHELL_ROOT,
                )
                st.success(f"已新增人物：{selected_person_name}")
                st.rerun()
            else:
                st.error("請先填名字。")

    st.divider()
    st.markdown("#### 選擇人物")

    person_names = [person.get("name", "未命名") for person in people]
    if person_names:
        selected_index = person_names.index(selected_person_name) if selected_person_name in person_names else 0
        selected_person_name = st.selectbox("你現在要回覆誰？", person_names, index=selected_index)
        selected_person = next((person for person in people if person.get("name") == selected_person_name), {})

        with st.container(border=True):
            st.markdown(f"**人物：{selected_person.get('name', '未命名')}**")
            st.write(f"個性：{selected_person.get('personality', '（未填）')}")
            st.write(f"關係：{selected_person.get('relationship', '（未填）')}")
            st.write(f"他對你的重要性：{selected_person.get('importance_to_me', '（未填）')}")
            st.write(f"你對他的重要性：{selected_person.get('importance_to_them', '（未填）')}")
            st.write(f"補充：{selected_person.get('note', '（未填）')}")
            if is_close_friend(selected_person):
                st.caption("這個人物目前會被當成『比較熟／好朋友』來產生回覆。")
    else:
        selected_person = {}
        st.info("你還沒有新增人物，先建立一個。")

    st.divider()
    st.markdown("#### 對話情境")
    request_text = st.text_area(
        "對方要求",
        value=request_text,
        placeholder="例如：他問我假日要不要吃飯，但我要補習，時間不能配合",
        height=100,
    )
    chat_context = st.text_area(
        "聊天紀錄 / 對話內容",
        value=chat_context,
        placeholder="例如：我都跟他說今天不行、沒空、要跟別人走，但他還是一直問",
        height=130,
    )

    with st.expander("Discord 傳送設定", expanded=False):
        st.caption("填入 Discord 頻道的 Webhook URL 後，每個回答都可以一鍵送到那個頻道。Webhook URL 可以發訊息到該頻道，請不要公開截圖或貼給別人。")
        st.info(
            "Webhook 不在 Discord 個人設定裡。請用 Discord 桌面版或網頁版，到「伺服器設定」→「整合」→「Webhooks」建立。"
            "如果你找不到這個選項，通常代表你不是伺服器管理員、沒有「管理 Webhook」權限，或你想傳的是私人訊息/群組 DM。"
        )
        discord_webhook_url = st.text_input(
            "Discord Webhook URL",
            type="password",
            placeholder="https://discord.com/api/webhooks/...",
            key="tourist_discord_webhook_url",
        )
        discord_username = st.text_input(
            "Discord 顯示名稱",
            value=discord_username,
            placeholder="Reply Helper",
        )
        remember_discord_webhook = st.checkbox(
            "記住 webhook 到本機資料檔",
            value=remember_discord_webhook,
            help="關閉時，重新整理或換頁期間通常仍可用，但不會寫進這頁的 JSON 資料檔。",
        )

        test_col1, test_col2 = st.columns([1, 2])
        with test_col1:
            if st.button("測試 Discord", use_container_width=True):
                if not discord_webhook_url.strip():
                    st.warning("請先貼上 Discord Webhook URL。")
                else:
                    ok, message = send_to_discord_webhook(
                        discord_webhook_url,
                        "Discord 傳送測試：如果你看到這則訊息，代表設定成功。",
                        discord_username,
                    )
                    if ok:
                        st.success(message)
                    else:
                        st.error(message)
        with test_col2:
            st.caption("Discord Webhook 會送到指定頻道；如果要傳私人訊息，仍需要 Discord Bot 與使用者授權。")

    selector_col1, selector_col2 = st.columns(2)
    with selector_col1:
        tone_index = TONE_OPTIONS.index(tone_default)
        tone = st.radio("你比較想用哪種回法？", TONE_OPTIONS, index=tone_index)
    with selector_col2:
        length_index = LENGTH_OPTIONS.index(length_mode)
        length_mode = st.radio("回覆長度", LENGTH_OPTIONS, index=length_index)

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if st.button("生成 5 個回答", use_container_width=True):
            refresh_count = 0
            rejected_replies = []
            generated_replies = generate_replies(
                my_profile,
                selected_person,
                request_text,
                tone,
                chat_context,
                length_mode,
            )
    with action_col2:
        if st.button("這 5 個我都不要，換一批", use_container_width=True, disabled=not generated_replies):
            rejected_replies = dedupe_keep_order(rejected_replies + generated_replies)
            refresh_count += 1
            generated_replies = generate_replies(
                my_profile,
                selected_person,
                request_text,
                tone,
                chat_context,
                length_mode,
                rejected_replies=rejected_replies,
                refresh_count=refresh_count,
            )

    save_page_data(
        PAGE_NAME,
        {
            "my_profile": my_profile,
            "people": people,
            "selected_person_name": selected_person_name,
            "request_text": request_text,
            "tone": tone,
            "length_mode": length_mode,
            "chat_context": chat_context,
            "generated_replies": generated_replies,
            "rejected_replies": rejected_replies,
            "refresh_count": refresh_count,
            "discord_webhook_url": discord_webhook_url if remember_discord_webhook else "",
            "discord_username": discord_username,
            "remember_discord_webhook": remember_discord_webhook,
        },
        shell_root=SHELL_ROOT,
    )

    st.divider()
    st.markdown("#### 可直接回的短句")
    if generated_replies:
        if refresh_count:
            st.caption(f"已換第 {refresh_count + 1} 批，這批會避開前面被你按掉的回答。")
        for idx, reply in enumerate(generated_replies, start=1):
            st.markdown(f"**選項 {idx}**")
            st.code(reply, language="text")
            render_reply_actions(reply, idx)
            if st.button(
                "傳到 Discord",
                key=f"discord_send_{idx}_{refresh_count}",
                use_container_width=True,
            ):
                if not discord_webhook_url.strip():
                    st.warning("請先到「Discord 傳送設定」貼上 Webhook URL。")
                else:
                    ok, message = send_to_discord_webhook(discord_webhook_url, reply, discord_username)
                    if ok:
                        st.success(f"選項 {idx}：{message}")
                    else:
                        st.error(f"選項 {idx}：{message}")
    else:
        st.info("先選人物、填對話情境，再按「生成 5 個回答」。")

    st.divider()
    st.markdown("#### 給 Agent 的摘要")
    extra = format_extra_context(
        PAGE_NAME,
        共享資料檔=str(shared_data_path(PAGE_NAME, shell_root=SHELL_ROOT)),
        目前選擇人物=selected_person_name or "（未選擇）",
        我的講話口氣=my_profile.get("my_tone", "") or "（未填）",
        對方要求=request_text or "（未填）",
        聊天紀錄=chat_context or "（未填）",
        回覆語氣=tone,
        回覆長度=length_mode,
        生成回答數量=len(generated_replies),
        已刷新批次=refresh_count,
        已排除回答數=len(rejected_replies),
    )
    st.code(extra, language="text")

    return extra


page_shell(
    PAGE_NAME,
    "改成更實用的回覆語氣選項，並支援超短版、正常版、帶理由版。",
    render_main,
    page_name=PAGE_NAME,
)
