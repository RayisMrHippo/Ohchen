import base64
import copy
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    message_chunk_to_message,
)
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI


WORKSPACE = Path.cwd().resolve()
MEMORY_DIR = WORKSPACE / "memory"
MEMORY_PATH = MEMORY_DIR / "MEMORY.md"
MEMORY_HISTORY_PATH = MEMORY_DIR / "HISTORY.md"
TOKEN_BUDGET = int(os.getenv("TOKEN_BUDGET", "8000"))
MEMORY_MAX_CHARS = int(os.getenv("MEMORY_MAX_CHARS", "6000"))
CONSOLIDATION_MAX_RETRIES = int(os.getenv("CONSOLIDATION_MAX_RETRIES", "3"))
COMPACTABLE = {"read_file", "exec", "grep", "glob", "web_search", "web_fetch", "list_dir"}
TOOL_MISSING_TEXT = "[Tool result unavailable - call was interrupted or lost]"


def _runtime_env_note() -> str:
    sys_name = platform.system()
    shell_hint = (
        "exec 在 PowerShell 下執行；勿用 <<、heredoc、bash -c。"
        if os.name == "nt"
        else "exec 在系統 shell 下執行；多行腳本仍請 write_file 後 uv run。"
    )
    return (
        f"\n\n【執行環境】{sys_name}（os.name={os.name}）；專案根目錄為 {WORKSPACE}。"
        f"\n{shell_hint}"
    )


def get_identity() -> str:
    """WG-12: 課堂人設、顯示名稱、執行環境與 exec 注意事項。"""
    system_text = (
        "你是課堂程式助教，請使用繁體中文回答。"
        "遇到算術、檔案、目錄或 shell 需求時，必須優先使用可用工具，不要只用文字猜測。"
    )
    nick = "法鬥超人"
    exec_note = (
        "\n\n【exec 注意】"
        "\n- 請依上方【執行環境】選擇相容的 shell 指令，勿假設為 Linux Bash。"
        "\n- 檔案操作請用 read_file/write_file/edit_file/list_dir；shell 指令才用 exec。"
        "\n- 若要執行 Python：先用 write_file 寫入 .py，再 exec「uv run python 相對路徑」。"
    )
    return (
        f"{system_text}\n\n【本場次顯示名稱】{nick}"
        f"{_runtime_env_note()}{exec_note}"
    )


def resolve_workspace_path(path: str) -> Path:
    raw = Path(path)
    if raw.is_absolute():
        raise PermissionError("absolute paths are not allowed")
    target = (WORKSPACE / raw).resolve()
    try:
        target.relative_to(WORKSPACE)
    except ValueError as exc:
        raise PermissionError(f"path is outside workspace: {path}") from exc
    return target


@tool("read_file")
def read_file(path: str, offset: int = 1, limit: int = 200) -> str:
    """讀取 workspace 內 UTF-8 文字檔，回傳帶行號內容。"""
    try:
        target = resolve_workspace_path(path)
        if not target.is_file():
            return f"Error: not a file: {path}"
        lines = target.read_text(encoding="utf-8").splitlines()
        start = max(offset - 1, 0)
        end = min(start + limit, len(lines))
        return "\n".join(f"{i + 1}| {line}" for i, line in enumerate(lines[start:end], start))
    except Exception as exc:
        return f"Error: {exc}"


@tool("write_file")
def write_file(path: str, content: str) -> str:
    """整檔覆寫寫入 UTF-8 文字檔，必要時建立父資料夾。"""
    try:
        target = resolve_workspace_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} characters to {path}"
    except Exception as exc:
        return f"Error: {exc}"


@tool("edit_file")
def edit_file(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
    """在既有檔案中把 old_text 換成 new_text，預設僅允許單一命中。"""
    try:
        target = resolve_workspace_path(path)
        if not target.is_file():
            return f"Error: not a file: {path}"
        text = target.read_text(encoding="utf-8")
        count = text.count(old_text)
        if count == 0:
            return "Error: old_text not found"
        if count > 1 and not replace_all:
            return "Error: old_text appears multiple times; provide more context or set replace_all=True"
        target.write_text(text.replace(old_text, new_text, -1 if replace_all else 1), encoding="utf-8")
        return f"edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


@tool("list_dir")
def list_dir(path: str = ".", recursive: bool = False, max_entries: int = 200) -> str:
    """列出 workspace 內資料夾內容。"""
    try:
        root = resolve_workspace_path(path)
        if not root.is_dir():
            return f"Error: not a directory: {path}"
        iterator = root.rglob("*") if recursive else root.iterdir()
        rows: list[str] = []
        for index, item in enumerate(sorted(iterator), start=1):
            if index > max_entries:
                rows.append(f"... truncated after {max_entries} entries")
                break
            rel = item.relative_to(WORKSPACE).as_posix()
            suffix = "/" if item.is_dir() else ""
            rows.append(f"{rel}{suffix}")
        return "\n".join(rows) if rows else "(empty)"
    except Exception as exc:
        return f"Error: {exc}"


@tool("exec")
def exec_workspace(command: str, timeout: int = 30) -> str:
    """在 workspace 內執行單行 shell 指令，回傳 exit code 與輸出摘要。"""
    lowered = command.lower()
    dangerous = ["rm -rf", "del /f", "rmdir /s", "format", "shutdown"]
    if any(part in lowered for part in dangerous):
        return "Error: command blocked by safety policy"
    if timeout < 1 or timeout > 120:
        return "Error: timeout must be between 1 and 120 seconds"
    try:
        completed = subprocess.run(
            command,
            cwd=WORKSPACE,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        output = (stdout + ("\n" if stdout and stderr else "") + stderr).strip()
        if len(output) > 4000:
            output = output[:4000] + "\n...[truncated]"
        return f"exit_code={completed.returncode}\n{output}"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as exc:
        return f"Error: {exc}"


TOOLS: list[BaseTool] = [read_file, write_file, edit_file, list_dir, exec_workspace]
TOOL_BY_NAME = {t.name: t for t in TOOLS}


def _tool_schema(tool_obj: BaseTool) -> dict[str, Any]:
    schema_model = getattr(tool_obj, "args_schema", None)
    if schema_model is not None and hasattr(schema_model, "model_json_schema"):
        schema = schema_model.model_json_schema()
        return {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
        }
    return {"type": "object", "properties": getattr(tool_obj, "args", {}) or {}, "required": []}


def _cast_value(value: Any, expected: str) -> Any:
    if expected == "integer" and isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return value
    if expected == "number" and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    if expected == "boolean" and isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return value


def cast_params(params: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)
    for key, spec in schema.get("properties", {}).items():
        if key in out:
            out[key] = _cast_value(out[key], spec.get("type", ""))
    return out


def validate_params(params: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    properties = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in params:
            errors.append(f"missing required field: {key}")
    for key, value in params.items():
        if key not in properties:
            errors.append(f"unknown field: {key}")
            continue
        expected = properties[key].get("type")
        if expected == "string" and not isinstance(value, str):
            errors.append(f"{key} must be string")
        elif expected == "integer" and not isinstance(value, int):
            errors.append(f"{key} must be integer")
        elif expected == "number" and not isinstance(value, (int, float)):
            errors.append(f"{key} must be number")
        elif expected == "boolean" and not isinstance(value, bool):
            errors.append(f"{key} must be boolean")
    return errors


def prepare_tool_call(name: str, raw: Any) -> tuple[BaseTool | None, dict[str, Any], str | None]:
    tool_obj = TOOL_BY_NAME.get(name)
    if tool_obj is None:
        return None, {}, f"unknown tool: {name}"
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None, {}, "tool arguments must be a JSON object"
    if not isinstance(raw, dict):
        return None, {}, "tool arguments must be a dict"
    schema = _tool_schema(tool_obj)
    params = cast_params(raw, schema)
    errors = validate_params(params, schema)
    if errors:
        return None, params, "; ".join(errors)
    return tool_obj, params, None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default_metadata(created_at: str | None = None) -> dict[str, Any]:
    now = _now()
    return {
        "_type": "metadata",
        "key": "session",
        "created_at": created_at or now,
        "updated_at": now,
        "metadata": {},
        "last_consolidated": 0,
    }


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    return str(content)


def _message_to_row(message: BaseMessage) -> dict[str, Any] | None:
    ts = _now()
    if isinstance(message, HumanMessage):
        row: dict[str, Any] = {
            "role": "user",
            "content": _text_from_content(message.content),
            "timestamp": ts,
        }
        image_path = message.additional_kwargs.get("image_path")
        media_type = message.additional_kwargs.get("media_type")
        if image_path:
            row["image_path"] = image_path
            if media_type:
                row["media_type"] = media_type
        return row
    if isinstance(message, AIMessage):
        row = {"role": "assistant", "content": _text_from_content(message.content), "timestamp": ts}
        if message.tool_calls:
            row["tool_calls"] = message.tool_calls
        return row
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "content": _text_from_content(message.content),
            "tool_call_id": message.tool_call_id,
            "name": getattr(message, "name", None),
            "timestamp": ts,
        }
    return None


def load_user_row_to_history_human(row: dict[str, Any]) -> HumanMessage:
    text = str(row.get("content", ""))
    image_path = row.get("image_path")
    if not image_path:
        return HumanMessage(content=text)
    media_type = row.get("media_type") or guess_media_type(Path(str(image_path)))
    placeholder = f"[此回合曾附圖，路徑：{image_path}]"
    if media_type:
        placeholder += f"（media_type={media_type}）"
    return HumanMessage(
        content=f"{text}\n\n{placeholder}",
        additional_kwargs={"image_path": image_path, "media_type": media_type},
    )


def load_session_jsonl(path: str) -> tuple[list[BaseMessage], dict[str, Any] | None]:
    target = Path(path)
    if not target.exists():
        return [], None
    messages: list[BaseMessage] = []
    meta: dict[str, Any] | None = None
    with target.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj: Any = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("_type") == "metadata":
                meta = obj
                continue
            role = obj.get("role")
            if role == "user":
                messages.append(load_user_row_to_history_human(obj))
            elif role == "assistant":
                tool_calls = obj.get("tool_calls")
                if tool_calls:
                    messages.append(AIMessage(content=str(obj.get("content", "")), tool_calls=tool_calls))
                else:
                    messages.append(AIMessage(content=str(obj.get("content", ""))))
            elif role == "tool":
                messages.append(
                    ToolMessage(
                        content=str(obj.get("content", "")),
                        tool_call_id=str(obj.get("tool_call_id") or ""),
                        name=obj.get("name"),
                    )
                )
    return messages, meta


def save_session_jsonl(
    path: str,
    messages: list[BaseMessage],
    existing_meta: dict[str, Any] | None,
    last_consolidated: int,
) -> dict[str, Any]:
    now = _now()
    meta = dict(existing_meta) if existing_meta is not None else _default_metadata(created_at=now)
    meta["_type"] = "metadata"
    meta["key"] = meta.get("key", "session")
    meta.setdefault("created_at", now)
    meta["updated_at"] = now
    meta["last_consolidated"] = max(0, last_consolidated)

    lines = [json.dumps(meta, ensure_ascii=False)]
    for message in messages:
        row = _message_to_row(message)
        if row is not None:
            lines.append(json.dumps(row, ensure_ascii=False))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return meta


def estimate_message_tokens(message: BaseMessage) -> int:
    content = message.content
    if isinstance(content, str):
        base = len(content)
    elif isinstance(content, list):
        base = sum(len(str(block.get("text", ""))) for block in content if isinstance(block, dict))
    else:
        base = len(str(content))
    if isinstance(message, AIMessage) and message.tool_calls:
        base += len(json.dumps(message.tool_calls, ensure_ascii=False))
    return base


def pick_consolidation_boundary(
    messages: list[BaseMessage],
    last_consolidated: int,
    tokens_to_remove: int,
) -> tuple[int, int] | None:
    start = last_consolidated
    if start >= len(messages) or tokens_to_remove <= 0:
        return None
    removed_tokens = 0
    last_boundary: tuple[int, int] | None = None
    for idx in range(start, len(messages)):
        message = messages[idx]
        if idx > start and isinstance(message, HumanMessage):
            last_boundary = (idx, removed_tokens)
            if removed_tokens >= tokens_to_remove:
                return last_boundary
        removed_tokens += estimate_message_tokens(message)
    return last_boundary


def request_cost_chars(system_str: str, messages: list[BaseMessage]) -> int:
    return len(system_str) + sum(estimate_message_tokens(m) for m in messages)


def memory_block_for_system() -> str:
    if not MEMORY_PATH.exists():
        return ""
    body = MEMORY_PATH.read_text(encoding="utf-8").strip()
    if not body:
        return ""
    if len(body) > MEMORY_MAX_CHARS:
        body = body[-MEMORY_MAX_CHARS:]
    return f"## Long-term Memory\n\n{body}"


def append_memory_history(entry: str, failed: bool = False) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    one_line = " ".join(entry.split())
    if len(one_line) > 800:
        one_line = one_line[:800] + "..."
    prefix = "[CONSOLIDATION-FAILED] " if failed else ""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with MEMORY_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {prefix}{one_line}\n")


def _format_messages_for_memory(messages: list[BaseMessage]) -> str:
    rows: list[str] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        elif isinstance(message, ToolMessage):
            role = "tool"
        else:
            role = "message"
        rows.append(f"{role}: {_text_from_content(message.content)}")
    return "\n\n".join(rows)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def consolidate_chunk(
    llm: ChatOpenAI,
    chunk: list[BaseMessage],
    current_memory: str,
) -> tuple[str, str] | None:
    prompt = (
        "請把舊對話濃縮成長期記憶。只輸出 JSON 物件，且只有兩個字串鍵："
        "history_entry（單行摘要）與 memory_update（完整取代 MEMORY.md 的 markdown）。"
        "\n\n既有 MEMORY.md：\n"
        f"{current_memory or '(empty)'}\n\n待整併 chunk：\n{_format_messages_for_memory(chunk)}"
    )
    for _ in range(max(CONSOLIDATION_MAX_RETRIES, 1)):
        response = llm.invoke([SystemMessage(content=get_identity()), HumanMessage(content=prompt)])
        obj = _extract_json_object(str(response.content))
        if obj and isinstance(obj.get("history_entry"), str) and isinstance(obj.get("memory_update"), str):
            return obj["history_entry"], obj["memory_update"]
    return None


def maybe_consolidate_memory(
    llm: ChatOpenAI,
    history: list[BaseMessage],
    session_path: str,
    session_meta: dict[str, Any] | None,
    last_consolidated: int,
    system_str: str,
    human_message: HumanMessage,
) -> tuple[int, dict[str, Any] | None]:
    while request_cost_chars(system_str, [*history[last_consolidated:], human_message]) > TOKEN_BUDGET:
        boundary = pick_consolidation_boundary(history, last_consolidated, TOKEN_BUDGET // 2)
        if boundary is None:
            break
        idx, _ = boundary
        chunk = history[last_consolidated:idx]
        if not chunk:
            break
        current_memory = MEMORY_PATH.read_text(encoding="utf-8") if MEMORY_PATH.exists() else ""
        result = consolidate_chunk(llm, chunk, current_memory)
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if result is None:
            append_memory_history(f"failed to consolidate messages {last_consolidated}:{idx}", failed=True)
        else:
            history_entry, memory_update = result
            MEMORY_PATH.write_text(memory_update, encoding="utf-8")
            append_memory_history(history_entry, failed=False)
        last_consolidated = idx
        session_meta = save_session_jsonl(session_path, history, session_meta, last_consolidated)
        system_str = build_system_prompt(SkillsLoader(WORKSPACE, WORKSPACE / "builtin_skills"))
        if request_cost_chars(system_str, [*history[last_consolidated:], human_message]) <= TOKEN_BUDGET // 2:
            break
    return last_consolidated, session_meta


def build_messages_for_model(
    messages: list[dict[str, Any]],
    *,
    max_chars: int,
    max_tool_chars: int,
    keep_recent_tools: int,
) -> list[dict[str, Any]]:
    out = [dict(m) for m in messages]

    known_tool_call_ids: set[str] = set()
    filtered: list[dict[str, Any]] = []
    for msg in out:
        if msg.get("role") == "tool" and msg.get("tool_call_id") not in known_tool_call_ids:
            continue
        filtered.append(msg)
        if msg.get("role") == "assistant":
            for call in msg.get("tool_calls") or []:
                call_id = _tool_call_id(call)
                if call_id:
                    known_tool_call_ids.add(call_id)
    out = filtered

    tool_ids_after = {m.get("tool_call_id") for m in out if m.get("role") == "tool"}
    repaired: list[dict[str, Any]] = []
    for msg in out:
        repaired.append(msg)
        if msg.get("role") == "assistant":
            for call in msg.get("tool_calls") or []:
                call_id = _tool_call_id(call)
                if call_id and call_id not in tool_ids_after:
                    repaired.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": _tool_call_name(call) or "unknown",
                            "content": TOOL_MISSING_TEXT,
                        }
                    )
    out = repaired

    for msg in out:
        if msg.get("role") == "tool" and isinstance(msg.get("content"), str):
            content = msg["content"]
            if len(content) > max_tool_chars:
                msg["content"] = content[:max_tool_chars] + "\n\n[truncated]"

    compact_indices = [
        i
        for i, msg in enumerate(out)
        if msg.get("role") == "tool" and msg.get("name") in COMPACTABLE
    ]
    for i in compact_indices[: max(0, len(compact_indices) - keep_recent_tools)]:
        content = str(out[i].get("content", ""))
        if len(content) >= 500:
            out[i]["content"] = f"[{out[i].get('name')} result omitted from context]"

    def cost(items: list[dict[str, Any]]) -> int:
        return sum(len(str(m.get("content", ""))) for m in items)

    while cost(out) > max_chars:
        user_indices = [i for i, msg in enumerate(out) if msg.get("role") == "user"]
        if len(user_indices) <= 1:
            break
        start = user_indices[0]
        end = user_indices[1]
        del out[start:end]
    if out and out[0].get("role") != "system":
        pass
    return out


def _tool_call_id(call: Any) -> str | None:
    if isinstance(call, dict):
        return call.get("id")
    return getattr(call, "id", None)


def _tool_call_name(call: Any) -> str | None:
    if isinstance(call, dict):
        if "name" in call:
            return call.get("name")
        function = call.get("function")
        if isinstance(function, dict):
            return function.get("name")
    return getattr(call, "name", None)


@dataclass
class SkillEntry:
    name: str
    path: Path
    source: str
    description: str
    always: bool
    body: str


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        return {}, text
    meta: dict[str, str] = {}
    for raw in lines[1:end]:
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        meta[key.strip()] = value.strip()
    body = "\n".join(lines[end + 1 :]).strip()
    return meta, body


class SkillsLoader:
    def __init__(self, workspace: Path, builtin_skills_dir: Path) -> None:
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir

    def _entries_from_dir(self, root: Path, source: str, skip: set[str]) -> list[SkillEntry]:
        if not root.exists():
            return []
        entries: list[SkillEntry] = []
        for skill_dir in sorted(root.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not skill_file.exists() or skill_dir.name in skip:
                continue
            text = skill_file.read_text(encoding="utf-8")
            meta, body = split_frontmatter(text)
            entries.append(
                SkillEntry(
                    name=skill_dir.name,
                    path=skill_file,
                    source=source,
                    description=meta.get("description") or skill_dir.name,
                    always=meta.get("always", "false").lower() == "true",
                    body=body,
                )
            )
        return entries

    def list_skills(self) -> list[SkillEntry]:
        workspace_entries = self._entries_from_dir(self.workspace_skills, "workspace", set())
        workspace_names = {entry.name for entry in workspace_entries}
        builtin_entries = self._entries_from_dir(self.builtin_skills, "builtin", workspace_names)
        return workspace_entries + builtin_entries

    def load_skill(self, name: str) -> str | None:
        for root in (self.workspace_skills, self.builtin_skills):
            path = root / name / "SKILL.md"
            if path.exists():
                return path.read_text(encoding="utf-8")
        return None


def build_skills_summary(entries: list[SkillEntry]) -> str:
    summarized = [entry for entry in entries if not entry.always]
    return "\n".join(
        f"- **{entry.name}**：{entry.description} `{entry.path.relative_to(WORKSPACE).as_posix()}`"
        for entry in summarized
    )


def build_system_prompt(loader: SkillsLoader) -> str:
    parts: list[str] = [get_identity()]
    memory = memory_block_for_system()
    if memory:
        parts.append(memory)
    entries = loader.list_skills()
    active = [entry for entry in entries if entry.always]
    if active:
        body = "\n\n---\n\n".join(f"### Skill: {entry.name}\n\n{entry.body}" for entry in active)
        parts.append(f"# Active Skills\n\n{body}")
    summary = build_skills_summary(entries)
    if summary:
        intro = (
            "以下是可用技能摘要。需要使用某個一般 skill 時，請先用 read_file 讀取清單中的 "
            "SKILL.md 路徑；若該技能需要套件或環境，先依該檔或專案說明安裝。"
        )
        parts.append(f"# Skills\n\n{intro}\n\n{summary}")
    return "\n\n---\n\n".join(parts)


def ensure_demo_skills() -> None:
    examples = {
        WORKSPACE / "skills" / "class-helper" / "SKILL.md": """---
name: class-helper
description: 協助學生把問題拆成步驟，適合卡關時使用。
always: false
---

# Class Helper
先問學生目前做到哪一步，再給一個最小提示，不直接給完整答案。
""",
        WORKSPACE / "builtin_skills" / "session-rules" / "SKILL.md": """---
name: session-rules
description: 永遠提醒 agent 分離 system、history 與本輪輸入。
always: true
---

# Session Rules
送模前確認 system 只出現在 SystemMessage；history 只保存 user、assistant、tool。
""",
    }
    for path, content in examples.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


def image_bytes_to_data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def guess_media_type(path: Path, fallback: str = "image/png") -> str:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return fallback


def build_human_message_for_current_turn(text: str, image_rel: Path | None) -> HumanMessage:
    if image_rel is None:
        return HumanMessage(content=text)
    full = resolve_workspace_path(image_rel.as_posix())
    media_type = guess_media_type(full)
    if not full.is_file():
        print(f"[warn] missing image for current turn: {image_rel}")
        return HumanMessage(content=text, additional_kwargs={"image_path": image_rel.as_posix(), "media_type": media_type})
    url = image_bytes_to_data_url(full.read_bytes(), media_type)
    return HumanMessage(
        content=[
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": url}},
        ],
        additional_kwargs={"image_path": image_rel.as_posix(), "media_type": media_type},
    )


def _human_to_text_only_placeholder(message: HumanMessage) -> HumanMessage:
    content = message.content
    if isinstance(content, str):
        return copy.deepcopy(message)
    text = _text_from_content(content)
    image_path = message.additional_kwargs.get("image_path")
    media_type = message.additional_kwargs.get("media_type")
    if image_path:
        text = f"{text}\n\n[此回合曾附圖，路徑：{image_path}]"
        if media_type:
            text += f"（media_type={media_type}）"
    else:
        text = f"{text}\n\n[此回合曾附圖，歷史送模時不重送 image_url]"
    return HumanMessage(content=text, additional_kwargs=dict(message.additional_kwargs))


def messages_for_model(
    system_message: SystemMessage,
    history: list[BaseMessage],
    human_message: HumanMessage,
) -> list[BaseMessage]:
    out: list[BaseMessage] = [copy.deepcopy(system_message)]
    for message in history:
        item = copy.deepcopy(message)
        if isinstance(item, HumanMessage) and not isinstance(item.content, str):
            item = _human_to_text_only_placeholder(item)
        out.append(item)
    out.append(copy.deepcopy(human_message))
    return out


def stream_to_ai_message(llm: Any, messages: list[BaseMessage]) -> AIMessage:
    print("助手：", end="", flush=True)
    accumulated = None
    for chunk in llm.stream(messages):
        content = chunk.content
        if isinstance(content, str) and content:
            print(content, end="", flush=True)
        accumulated = chunk if accumulated is None else accumulated + chunk
    print()
    if accumulated is None:
        return AIMessage(content="")
    message = message_chunk_to_message(accumulated)
    if isinstance(message, AIMessage):
        return message
    return AIMessage(content=_text_from_content(message.content))


def run_react_turn(
    llm_with_tools: Any,
    system_message: SystemMessage,
    past: list[BaseMessage],
    human_message: HumanMessage,
) -> list[BaseMessage]:
    turn_messages: list[BaseMessage] = [human_message]
    messages = messages_for_model(system_message, past, human_message)
    while True:
        response = stream_to_ai_message(llm_with_tools, messages)
        turn_messages.append(response)
        messages.append(response)
        if not response.tool_calls:
            break
        for call in response.tool_calls:
            name = call.get("name", "")
            args = call.get("args", {})
            call_id = call.get("id") or name
            tool_obj, params, error = prepare_tool_call(name, args)
            if error:
                content = f"Error: {error}"
            else:
                print(f"[tool] {name}({params})")
                try:
                    content = str(tool_obj.invoke(params)) if tool_obj is not None else "Error: missing tool"
                except Exception as exc:
                    content = f"Error: {exc}"
            tool_message = ToolMessage(content=content, tool_call_id=call_id, name=name)
            turn_messages.append(tool_message)
            messages.append(tool_message)
    return turn_messages


def parse_user_input(raw: str) -> tuple[str, Path | None]:
    if raw.startswith("/image "):
        rest = raw[len("/image ") :].strip()
        if not rest:
            return "", None
        if " " in rest:
            image, text = rest.split(" ", 1)
        else:
            image = rest
            text = input("圖片問題：").strip()
        return text, Path(image)
    return raw, None


def main() -> None:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("MODEL_NAME", "gpt-4o")
    base_url = os.getenv("BASE_URL") or None
    session_path = os.getenv("SESSION_JSONL_PATH", "session.jsonl")

    if not api_key:
        print("OPENAI_API_KEY: 尚未設定")
        return

    ensure_demo_skills()
    loader = SkillsLoader(WORKSPACE, WORKSPACE / "builtin_skills")
    history, session_meta = load_session_jsonl(session_path)
    last_consolidated = int((session_meta or {}).get("last_consolidated", 0) or 0)

    llm = ChatOpenAI(model=model_name, base_url=base_url, api_key=api_key)
    llm_with_tools = llm.bind_tools(TOOLS)

    print(f"MODEL_NAME: {model_name}")
    print(f"SESSION_JSONL_PATH: {session_path}")
    print("輸入 STOP 結束；附圖格式：/image 相對路徑 你的問題")

    while True:
        raw = input("\nYou: ").strip()
        if not raw:
            continue
        if raw.upper() == "STOP":
            print("對話結束")
            break

        user_text, image_rel = parse_user_input(raw)
        if not user_text:
            continue
        human_message = build_human_message_for_current_turn(user_text, image_rel)

        system_str = build_system_prompt(loader)
        last_consolidated, session_meta = maybe_consolidate_memory(
            llm,
            history,
            session_path,
            session_meta,
            last_consolidated,
            system_str,
            human_message,
        )
        system_str = build_system_prompt(loader)
        system_message = SystemMessage(content=system_str)

        past0 = history[last_consolidated:]
        cost = request_cost_chars(system_str, [*past0, human_message])
        if cost <= TOKEN_BUDGET:
            past = past0
        else:
            tokens_to_remove = max(0, cost - TOKEN_BUDGET // 2)
            boundary = pick_consolidation_boundary(history, last_consolidated, tokens_to_remove)
            past = history[boundary[0] :] if boundary is not None else past0

        turn_messages = run_react_turn(llm_with_tools, system_message, past, human_message)
        history.extend(turn_messages)
        session_meta = save_session_jsonl(session_path, history, session_meta, last_consolidated)


if __name__ == "__main__":
    main()
