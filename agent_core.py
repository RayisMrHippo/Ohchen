from __future__ import annotations

import base64
import copy
import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    message_chunk_to_message,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


WORKSPACE = Path.cwd().resolve()
DEFAULT_SESSION_PATH = "session.jsonl"
DEFAULT_TOKEN_BUDGET = 200000
MEMORY_PATH = Path("memory") / "MEMORY.md"
HISTORY_PATH = Path("memory") / "HISTORY.md"
MEMORY_TEMPLATE_PATH = Path("templates") / "memory" / "MEMORY.md"
MEMORY_MERGE_PROMPT_PATH = Path("prompts") / "memory_merge.md"


def get_token_budget() -> int:
    raw = os.getenv("TOKEN_BUDGET")
    if raw is None:
        return DEFAULT_TOKEN_BUDGET
    try:
        return max(1000, int(raw))
    except ValueError:
        return DEFAULT_TOKEN_BUDGET


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_workspace_path(path: str | Path) -> Path:
    raw = Path(path)
    if raw.is_absolute():
        raise PermissionError("absolute paths are not allowed")
    target = (WORKSPACE / raw).resolve()
    try:
        target.relative_to(WORKSPACE)
    except ValueError as exc:
        raise PermissionError(f"path is outside workspace: {path}") from exc
    return target


@tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers and return the numeric result."""
    return float(a) + float(b)


@tool("read_file")
def read_file(path: str, offset: int = 1, limit: int = 200) -> str:
    """Read a UTF-8 text file inside the workspace with line numbers."""
    try:
        target = resolve_workspace_path(path)
        if not target.is_file():
            return f"Error: not a file: {path}"
        lines = target.read_text(encoding="utf-8").splitlines()
        start = max(offset - 1, 0)
        end = min(start + max(limit, 1), len(lines))
        return "\n".join(f"{i + 1}| {line}" for i, line in enumerate(lines[start:end], start))
    except Exception as exc:
        return f"Error: {exc}"


@tool("write_file")
def write_file(path: str, content: str) -> str:
    """Write UTF-8 text to a workspace-relative path."""
    try:
        target = resolve_workspace_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} characters to {path}"
    except Exception as exc:
        return f"Error: {exc}"


@tool("edit_file")
def edit_file(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
    """Replace text in a workspace file."""
    try:
        target = resolve_workspace_path(path)
        text = target.read_text(encoding="utf-8")
        count = text.count(old_text)
        if count == 0:
            return "Error: old_text not found"
        if count > 1 and not replace_all:
            return "Error: old_text appears multiple times"
        target.write_text(text.replace(old_text, new_text, -1 if replace_all else 1), encoding="utf-8")
        return f"edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


@tool("list_dir")
def list_dir(path: str = ".", recursive: bool = False, max_entries: int = 200) -> str:
    """List files or directories inside the workspace."""
    try:
        root = resolve_workspace_path(path)
        if not root.is_dir():
            return f"Error: not a directory: {path}"
        iterator = root.rglob("*") if recursive else root.iterdir()
        entries = [str(item.relative_to(WORKSPACE)) for item in iterator][:max_entries]
        return "\n".join(entries) if entries else "(empty)"
    except Exception as exc:
        return f"Error: {exc}"


@tool("exec")
def exec_workspace(command: str, timeout: int = 30) -> str:
    """Run a shell command in the workspace and return captured output."""
    blocked = ("rm -rf", "del /f", "rmdir /s", "format ", "shutdown")
    lowered = command.lower()
    if any(part in lowered for part in blocked):
        return "Error: blocked dangerous command"

    child_env = os.environ.copy()
    child_env.setdefault("PYTHONUTF8", "1")
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    run_kw: dict[str, Any] = {
        "cwd": str(WORKSPACE),
        "shell": True,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": max(1, min(timeout, 120)),
        "env": child_env,
    }
    if os.name == "nt":
        run_kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        result = subprocess.run(command, **run_kw)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if not output:
            output = "(no stdout or stderr)"
        if len(output) > 4000:
            output = output[:4000] + "\n\n[truncated]"
        return f"exit_code={result.returncode}\n{output}"
    except Exception as exc:
        return f"Error: {exc}"


TOOLS = [add_numbers, read_file, write_file, edit_file, list_dir, exec_workspace]
TOOL_BY_NAME: dict[str, Any] = {item.name: item for item in TOOLS}


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
    return meta, "\n".join(lines[end + 1 :]).strip()


@dataclass
class SkillEntry:
    name: str
    path: Path
    source: str
    description: str
    always: bool
    body: str


class SkillsLoader:
    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None) -> None:
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir or workspace / "builtin_skills"

    def _entries_from_dir(self, root: Path, source: str, skip: set[str]) -> list[SkillEntry]:
        if not root.exists():
            return []
        entries: list[SkillEntry] = []
        for skill_dir in root.iterdir():
            skill_file = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not skill_file.exists() or skill_dir.name in skip:
                continue
            text = skill_file.read_text(encoding="utf-8", errors="replace")
            meta, body = split_frontmatter(text)
            entries.append(
                SkillEntry(
                    name=skill_dir.name,
                    path=skill_file,
                    source=source,
                    description=meta.get("description", skill_dir.name),
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
            skill_file = root / name / "SKILL.md"
            if skill_file.exists():
                return skill_file.read_text(encoding="utf-8", errors="replace")
        return None


def get_identity() -> str:
    return (
        "You are a helpful agent running in a local workshop workspace. "
        "Use tools carefully, prefer workspace-relative paths, and explain actions clearly. "
        "You may read, write, edit, list files, run safe commands, and answer directly."
    )


def ensure_memory_files() -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MEMORY_PATH.exists():
        if MEMORY_TEMPLATE_PATH.exists():
            MEMORY_PATH.write_text(MEMORY_TEMPLATE_PATH.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        else:
            MEMORY_PATH.write_text("# Long-term Memory\n\n## User Information\n## Preferences\n## Project Context\n## Important Notes\n", encoding="utf-8")
    if not HISTORY_PATH.exists():
        HISTORY_PATH.write_text("# Memory History\n\n", encoding="utf-8")


def memory_block_for_system() -> str:
    ensure_memory_files()
    text = MEMORY_PATH.read_text(encoding="utf-8", errors="replace").strip()
    return f"# Long-term Memory\n\n{text}" if text else ""


def build_skills_summary(entries: list[SkillEntry]) -> str:
    summarized = [entry for entry in entries if not entry.always]
    if not summarized:
        return ""
    lines = ["# Skills", "Available skills can be loaded when relevant:"]
    for entry in summarized:
        lines.append(f"- {entry.name}: {entry.description} ({entry.path})")
    return "\n".join(lines)


def build_system_prompt(loader: SkillsLoader) -> str:
    parts = [get_identity()]
    memory = memory_block_for_system()
    if memory:
        parts.append(memory)
    entries = loader.list_skills()
    active = [entry for entry in entries if entry.always]
    if active:
        body = "\n\n---\n\n".join(f"### Skill: {entry.name}\n\n{entry.body}" for entry in active)
        parts.append("# Active Skills\n\n" + body)
    summary = build_skills_summary(entries)
    if summary:
        parts.append(summary)
    return "\n\n---\n\n".join(parts)


def _default_metadata() -> dict[str, Any]:
    stamp = now_iso()
    return {
        "_type": "metadata",
        "key": "session",
        "created_at": stamp,
        "updated_at": stamp,
        "metadata": {},
        "last_consolidated": 0,
    }


def _message_to_row(message: BaseMessage) -> dict[str, Any] | None:
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content if isinstance(message.content, str) else str(message.content), "timestamp": now_iso()}
    if isinstance(message, AIMessage):
        row: dict[str, Any] = {"role": "assistant", "content": message.content, "timestamp": now_iso()}
        if getattr(message, "tool_calls", None):
            row["tool_calls"] = message.tool_calls
        return row
    if isinstance(message, ToolMessage):
        return {"role": "tool", "name": message.name, "tool_call_id": message.tool_call_id, "content": message.content, "timestamp": now_iso()}
    return None


def save_session_jsonl(
    path: str,
    history: list[BaseMessage],
    session_meta: dict[str, Any] | None = None,
    last_consolidated: int | None = None,
) -> dict[str, Any]:
    meta = dict(session_meta or _default_metadata())
    meta["updated_at"] = now_iso()
    if last_consolidated is not None:
        meta["last_consolidated"] = last_consolidated
    rows = [meta]
    rows.extend(row for msg in history if (row := _message_to_row(msg)) is not None)
    target = resolve_workspace_path(path)
    target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return meta


def _row_to_message(row: dict[str, Any]) -> BaseMessage | None:
    role = row.get("role")
    if role == "user":
        return HumanMessage(content=row.get("content", ""))
    if role == "assistant":
        kwargs: dict[str, Any] = {}
        if row.get("tool_calls"):
            kwargs["tool_calls"] = row["tool_calls"]
        return AIMessage(content=row.get("content", ""), **kwargs)
    if role == "tool":
        return ToolMessage(content=row.get("content", ""), tool_call_id=row.get("tool_call_id", ""), name=row.get("name"))
    return None


def load_session_jsonl(path: str) -> tuple[list[BaseMessage], dict[str, Any] | None]:
    target = resolve_workspace_path(path)
    if not target.exists():
        return [], None
    history: list[BaseMessage] = []
    meta: dict[str, Any] | None = None
    for raw in target.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if row.get("_type") == "metadata":
            meta = row
            continue
        message = _row_to_message(row)
        if message is not None:
            history.append(message)
    return history, meta


def estimate_message_tokens(messages: list[BaseMessage]) -> int:
    chars = sum(len(str(message.content)) for message in messages)
    return max(1, chars // 4)


def load_memory_merge_prompt() -> str:
    if MEMORY_MERGE_PROMPT_PATH.exists():
        return MEMORY_MERGE_PROMPT_PATH.read_text(encoding="utf-8", errors="replace")
    return "Merge the conversation summary into the existing memory. Return concise markdown."


def consolidate_memory(llm: ChatOpenAI, history: list[BaseMessage], start: int, end: int) -> None:
    ensure_memory_files()
    pack = "\n".join(f"{type(msg).__name__}: {msg.content}" for msg in history[start:end])
    if not pack.strip():
        return
    prompt = load_memory_merge_prompt()
    current = MEMORY_PATH.read_text(encoding="utf-8", errors="replace")
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=f"Current memory:\n{current}\n\nConversation chunk:\n{pack}"),
    ]
    response = llm.invoke(messages)
    updated = str(response.content).strip()
    if updated:
        MEMORY_PATH.write_text(updated + "\n", encoding="utf-8")
        with HISTORY_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"\n## {now_iso()}\n\nConsolidated messages {start}:{end}.\n")


def ensure_budget_before_react(
    llm: ChatOpenAI,
    history: list[BaseMessage],
    last_consolidated: int,
    pending_human: HumanMessage,
) -> int:
    budget = get_token_budget()
    probe = history + [pending_human]
    if estimate_message_tokens(probe) <= budget:
        return last_consolidated
    if len(history) - last_consolidated < 4:
        return last_consolidated
    boundary = max(last_consolidated + 1, len(history) - 8)
    consolidate_memory(llm, history, last_consolidated, boundary)
    return boundary


def guess_media_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    return "image/png"


def image_bytes_to_data_url(data: bytes, media_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def build_human_message_for_current_turn(user_text: str, image_path: str | None = None) -> HumanMessage:
    if not image_path:
        return HumanMessage(content=user_text)
    target = resolve_workspace_path(image_path)
    if not target.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")
    media_type = guess_media_type(target)
    data_url = image_bytes_to_data_url(target.read_bytes(), media_type)
    return HumanMessage(
        content=[
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
    )


def history_human_placeholder(user_text: str, image_path: str | None, media_type: str | None) -> HumanMessage:
    if not image_path:
        return HumanMessage(content=user_text)
    suffix = f"\n\n[Attached image: {image_path}"
    if media_type:
        suffix += f"; media_type={media_type}"
    suffix += "]"
    return HumanMessage(content=user_text + suffix)


def _text_only_human(message: HumanMessage) -> HumanMessage:
    if isinstance(message.content, str):
        return message
    parts: list[str] = []
    for block in message.content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    text = "\n".join(part for part in parts if part).strip() or "[image message]"
    return HumanMessage(content=text + "\n\n[image omitted from prior history]")


def messages_for_model(
    system_message: SystemMessage,
    history: list[BaseMessage],
    human_message: HumanMessage,
) -> list[BaseMessage]:
    out: list[BaseMessage] = [copy.deepcopy(system_message)]
    for message in history:
        copied = copy.deepcopy(message)
        if isinstance(copied, HumanMessage) and not isinstance(copied.content, str):
            copied = _text_only_human(copied)
        out.append(copied)
    out.append(copy.deepcopy(human_message))
    return out


def _stream_model_response(
    llm_tools: Any,
    messages: list[BaseMessage],
    on_token: Callable[[str], None] | None = None,
) -> AIMessage:
    acc: AIMessageChunk | None = None
    for chunk in llm_tools.stream(messages):
        acc = chunk if acc is None else acc + chunk
        content = chunk.content
        if isinstance(content, str) and content:
            if on_token is not None:
                on_token(content)
            else:
                print(content, end="", flush=True)
    if acc is None:
        raise RuntimeError("model stream returned no chunks")
    return message_chunk_to_message(acc)


def run_react_turn(
    llm_tools: Any,
    system_message: SystemMessage,
    history: list[BaseMessage],
    human_message: HumanMessage,
    on_token: Callable[[str], None] | None = None,
) -> list[BaseMessage]:
    turn_messages: list[BaseMessage] = [human_message]
    while True:
        outbound = messages_for_model(system_message, history + turn_messages[:-1], turn_messages[-1])
        ai_message = _stream_model_response(llm_tools, outbound, on_token=on_token)
        turn_messages.append(ai_message)
        tool_calls = getattr(ai_message, "tool_calls", None) or []
        if not tool_calls:
            return turn_messages
        for call in tool_calls:
            name = call.get("name", "")
            args = call.get("args") or {}
            tool_obj = TOOL_BY_NAME.get(name)
            if tool_obj is None:
                content = f"Error: unknown tool {name}"
            else:
                try:
                    content = str(tool_obj.invoke(args))
                except Exception as exc:
                    content = f"Error: {exc}"
            turn_messages.append(ToolMessage(content=content, tool_call_id=call.get("id", ""), name=name))


class Agent:
    """Core WG-12 through WG-21 agent logic exposed through one chat API."""

    def __init__(
        self,
        *,
        session_path: str,
        history: list[BaseMessage],
        session_meta: dict[str, Any] | None,
        last_consolidated: int,
        llm: ChatOpenAI,
        llm_tools: Any,
        skills_loader: SkillsLoader,
    ) -> None:
        self.session_path = session_path
        self.history = history
        self.session_meta = session_meta
        self.last_consolidated = last_consolidated
        self.llm = llm
        self.llm_tools = llm_tools
        self.skills_loader = skills_loader

    @classmethod
    def from_env(cls, *, session_path: str | None = None) -> "Agent":
        load_dotenv()
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Missing OPENAI_API_KEY. Add it to .env before starting the agent.")
        resolved_path = session_path or os.getenv("SESSION_JSONL_PATH", DEFAULT_SESSION_PATH)
        history, session_meta = load_session_jsonl(resolved_path)
        last_consolidated = int((session_meta or {}).get("last_consolidated", 0) or 0)
        llm = ChatOpenAI(
            model=os.getenv("MODEL_NAME"),
            base_url=os.getenv("BASE_URL"),
            api_key=os.getenv("API_KEY"),
            temperature=0.2
            )
        return cls(
            session_path=resolved_path,
            history=history,
            session_meta=session_meta,
            last_consolidated=last_consolidated,
            llm=llm,
            llm_tools=llm.bind_tools(TOOLS),
            skills_loader=SkillsLoader(WORKSPACE),
        )

    def chat(
        self,
        user_text: str,
        *,
        image_path: str | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        media_type = guess_media_type(resolve_workspace_path(image_path)) if image_path else None
        history_human = history_human_placeholder(user_text, image_path, media_type)
        human_for_send = build_human_message_for_current_turn(user_text, image_path)
        self.last_consolidated = ensure_budget_before_react(
            self.llm,
            self.history,
            self.last_consolidated,
            history_human,
        )
        system_message = SystemMessage(content=build_system_prompt(self.skills_loader))
        turn_messages = run_react_turn(
            self.llm_tools,
            system_message,
            self.history,
            human_for_send,
            on_token=on_token,
        )
        if image_path:
            turn_messages[0] = history_human
        self.history.extend(turn_messages)
        self.session_meta = save_session_jsonl(
            self.session_path,
            self.history,
            self.session_meta,
            self.last_consolidated,
        )
        assistant_messages = [msg for msg in turn_messages if isinstance(msg, AIMessage)]
        return str(assistant_messages[-1].content) if assistant_messages else ""
