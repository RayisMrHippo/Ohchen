from __future__ import annotations

from agent_core import Agent, get_token_budget


def parse_image_command(user_line: str) -> tuple[str | None, str | None, bool]:
    if not user_line.startswith("/image "):
        return None, user_line, False
    rest = user_line[len("/image ") :].strip()
    if not rest:
        return None, None, True
    parts = rest.split(maxsplit=1)
    image_path = parts[0]
    if len(parts) == 1:
        return image_path, None, True
    return image_path, parts[1].strip(), False


def main() -> None:
    try:
        agent = Agent.from_env()
    except RuntimeError as exc:
        print(exc)
        return

    print("Agent ready. Type quit, exit, or q to leave.")
    print("Attach an image with /image path/to/image.png your question")
    print("Or set a pending image with /image path/to/image.png, then send the next message.")
    print(f"TOKEN_BUDGET={get_token_budget()} session={agent.session_path}")
    if agent.history:
        print(f"Loaded {len(agent.history)} prior messages; last_consolidated={agent.last_consolidated}")
    else:
        print("Starting a fresh session.")

    pending_image: str | None = None

    while True:
        user_line = input("\nYou: ").strip()
        if user_line.lower() in {"quit", "exit", "q"}:
            print("Bye.")
            break
        if not user_line:
            continue

        image_path, user_text, pending_only = parse_image_command(user_line)
        if pending_only and image_path is None:
            print("Usage: /image path/to/image.png optional question")
            continue
        if pending_only and image_path is not None:
            pending_image = image_path
            print(f"Image queued: {pending_image}")
            continue
        if image_path is None and pending_image is not None:
            image_path = pending_image
            pending_image = None
        if not user_text:
            continue

        print("\nAssistant: ", end="", flush=True)
        try:
            agent.chat(user_text, image_path=image_path)
        except FileNotFoundError as exc:
            print(f"\n{exc}")
        print()


if __name__ == "__main__":
    main()
