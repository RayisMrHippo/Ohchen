from __future__ import annotations

import asyncio
import base64
import os
import shutil
import uuid
from pathlib import Path

import chainlit as cl
from openai import OpenAI

from agent_core import Agent


UPLOADS_DIR = Path("uploads") / "chainlit"
GENERATED_DIR = Path("generated") / "chainlit"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
EDIT_KEYWORDS = (
    "/edit ",
    "edit",
    "modify",
    "retouch",
    "remove background",
    "replace background",
    "photoshop",
    "touch up",
    "change this image",
    "change this photo",
)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def new_agent() -> Agent:
    return Agent.from_env()


def get_agent() -> Agent:
    agent = cl.user_session.get("agent")
    if agent is None:
        agent = new_agent()
        cl.user_session.set("agent", agent)
    return agent


def looks_like_image_edit_request(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in EDIT_KEYWORDS)


def _is_image_element(element: object) -> bool:
    mime = str(getattr(element, "mime", "") or "").lower()
    path = Path(str(getattr(element, "path", "") or ""))
    return mime.startswith("image/") or path.suffix.lower() in IMAGE_EXTENSIONS


def persist_uploaded_image(message: cl.Message) -> str | None:
    elements = getattr(message, "elements", None) or []
    image_element = next((element for element in elements if _is_image_element(element)), None)
    if image_element is None:
        return None

    source = Path(str(getattr(image_element, "path", "") or ""))
    if not source.is_file():
        return None

    ensure_dir(UPLOADS_DIR)
    suffix = source.suffix.lower() or ".png"
    target = UPLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"
    shutil.copy2(source, target)
    return target.as_posix()


def edit_image_from_prompt(image_path: str, prompt: str) -> Path:
    api_key = os.getenv("OPENAI_IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_IMAGE_API_KEY or OPENAI_API_KEY for image editing.")

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENAI_IMAGE_BASE_URL") or None,
    )
    source = Path(image_path)
    if not source.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")

    ensure_dir(GENERATED_DIR)
    output_format = os.getenv("OPENAI_IMAGE_OUTPUT_FORMAT", "png")
    model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

    with source.open("rb") as image_file:
        result = client.images.edit(
            model=model,
            image=image_file,
            prompt=prompt,
            output_format=output_format,
        )

    item = result.data[0]
    if getattr(item, "b64_json", None):
        data = base64.b64decode(item.b64_json)
    elif getattr(item, "url", None):
        raise RuntimeError("Image edit returned a URL response; configure the API to return base64 output.")
    else:
        raise RuntimeError("Image edit did not return image data.")

    suffix = ".png" if output_format == "png" else f".{output_format}"
    target = GENERATED_DIR / f"edited-{uuid.uuid4().hex}{suffix}"
    target.write_bytes(data)
    return target


@cl.on_chat_start
async def on_chat_start() -> None:
    agent = new_agent()
    cl.user_session.set("agent", agent)
    await cl.Message(
        content=(
            "Agent ready. This UI uses your existing `Agent.chat(..., on_token=...)` path for streaming chat."
            "\nUpload an image and ask normally for vision tasks."
            "\nIf you want an actual image edit, send the image with a prompt starting with `/edit `."
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    agent = get_agent()
    image_path = persist_uploaded_image(message)

    if image_path and looks_like_image_edit_request(message.content):
        status = cl.Message(content="Editing image...")
        await status.send()
        try:
            edited_path = await asyncio.to_thread(edit_image_from_prompt, image_path, message.content)
        except Exception as exc:
            status.content = f"Image edit failed: {exc}"
            await status.update()
            return

        status.content = "Image edit complete."
        status.elements = [
            cl.Image(
                name=edited_path.name,
                path=str(edited_path),
                display="inline",
            )
        ]
        await status.update()
        return

    assistant_message = cl.Message(content="")
    await assistant_message.send()
    loop = asyncio.get_running_loop()

    def on_token(token: str) -> None:
        future = asyncio.run_coroutine_threadsafe(assistant_message.stream_token(token), loop)
        future.result()

    try:
        response = await asyncio.to_thread(
            agent.chat,
            message.content,
            image_path=image_path,
            on_token=on_token,
        )
        if not assistant_message.content:
            assistant_message.content = response
        await assistant_message.update()
    except Exception as exc:
        assistant_message.content = f"Error: {exc}"
        await assistant_message.update()
