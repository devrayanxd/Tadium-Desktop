"""
Tadium — main.py
Full backend: pywebview window, llama-cpp-python model loading,
agentic tool loop with permission gating, chat persistence.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

import pyautogui
import pyperclip
import webview
from PIL import ImageGrab
from llama_cpp import Llama
from playwright.sync_api import sync_playwright

# ── DIRECTORIES ───────────────────────────────────────────────────────────────
BASE_DIR   = Path(r"C:\Tadium")
MODELS_DIR = BASE_DIR / "models"
CHATS_DIR  = BASE_DIR / "chats"

for _d in (MODELS_DIR, CHATS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── GLOBAL STATE ──────────────────────────────────────────────────────────────
_llm:        Optional[Llama] = None
_model_name: str = ""
_window      = None          # set after webview.create_window

# ── PERMISSION GATE ───────────────────────────────────────────────────────────
_perm_event:   threading.Event = threading.Event()
_perm_allowed: bool = False

def _ask_permission(action: str, detail: str) -> bool:
    """
    Calls into JS to show the permission modal.
    Blocks until the user clicks Allow or Deny (or 2 min timeout → deny).
    """
    global _perm_allowed
    _perm_event.clear()
    _perm_allowed = False
    if _window:
        js = (
            f"requestPermission({json.dumps(action)}, {json.dumps(detail)})"
            ".then(r => pywebview.api._perm_answer(r))"
        )
        _window.evaluate_js(js)
    granted = _perm_event.wait(timeout=120)
    return _perm_allowed if granted else False


# ── TOOLS ─────────────────────────────────────────────────────────────────────
PERMISSION_REQUIRED = {
    "click", "type_text", "press_key",
    "write_file", "delete_file", "run_command",
    "open_app", "copy_to_clipboard",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "move_mouse",
            "description": "Move the mouse cursor to absolute screen coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X pixel coordinate"},
                    "y": {"type": "integer", "description": "Y pixel coordinate"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click at screen coordinates. button: left/right/middle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x":      {"type": "integer"},
                    "y":      {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                    "double": {"type": "boolean", "default": False},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type a string of text using the keyboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a key or hotkey combo, e.g. 'enter', 'ctrl+c', 'alt+f4'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Take a screenshot of the screen. Returns a base64 PNG so the agent can see what's on screen.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the mouse wheel at a screen position. Positive clicks = down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x":      {"type": "integer"},
                    "y":      {"type": "integer"},
                    "clicks": {"type": "integer"},
                },
                "required": ["x", "y", "clicks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read and return the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write (create or overwrite) a file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "default": 30},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_url",
            "description": "Open a URL in a headless browser and return the page title and text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_to_clipboard",
            "description": "Copy text to the system clipboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open an application by name or full path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string"},
                },
                "required": ["app"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are Tadium, a powerful AI agent that can control a Windows PC. "
    "You have tools to move the mouse, click, type, take screenshots, browse the web, "
    "read and write files, run shell commands, and more.\n\n"
    "Workflow:\n"
    "1. Understand what the user wants.\n"
    "2. Think through the steps needed.\n"
    "3. Use tools one at a time, checking results before proceeding.\n"
    "4. For any destructive or sensitive action, briefly explain what you are about to do.\n"
    "5. After completing a task, give a short summary of what was done.\n\n"
    "Be concise. Avoid unnecessary tool calls. If a task seems risky, confirm with the user first."
)


# ── TOOL EXECUTOR ─────────────────────────────────────────────────────────────
def _run_tool(name: str, args: dict) -> str:
    if name == "move_mouse":
        pyautogui.moveTo(args["x"], args["y"], duration=0.25)
        return f"Mouse moved to ({args['x']}, {args['y']})"

    elif name == "click":
        btn = args.get("button", "left")
        if args.get("double"):
            pyautogui.doubleClick(args["x"], args["y"], button=btn)
        else:
            pyautogui.click(args["x"], args["y"], button=btn)
        return f"Clicked {btn} at ({args['x']}, {args['y']})"

    elif name == "type_text":
        pyautogui.write(args["text"], interval=0.025)
        return f"Typed {len(args['text'])} characters"

    elif name == "press_key":
        keys = args["key"].split("+")
        if len(keys) > 1:
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(keys[0])
        return f"Pressed: {args['key']}"

    elif name == "screenshot":
        img = ImageGrab.grab()
        img = img.resize((img.width // 2, img.height // 2))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        import base64
        b64 = base64.b64encode(buf.getvalue()).decode()
        # Return a truncated description — full base64 would overflow context
        return f"[Screenshot taken: {img.width}x{img.height}px, base64 length={len(b64)}]"

    elif name == "scroll":
        pyautogui.scroll(args["clicks"], x=args["x"], y=args["y"])
        return f"Scrolled {args['clicks']} at ({args['x']}, {args['y']})"

    elif name == "read_file":
        p = Path(args["path"])
        if not p.exists():
            return f"File not found: {args['path']}"
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            return content[:5000] + ("…[truncated]" if len(content) > 5000 else "")
        except Exception as e:
            return f"Read error: {e}"

    elif name == "write_file":
        p = Path(args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"], encoding="utf-8")
        return f"Wrote {len(args['content'])} chars to {args['path']}"

    elif name == "delete_file":
        p = Path(args["path"])
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink(missing_ok=True)
        return f"Deleted: {args['path']}"

    elif name == "run_command":
        timeout = int(args.get("timeout", 30))
        try:
            res = subprocess.run(
                args["command"], shell=True,
                capture_output=True, text=True, timeout=timeout,
            )
            out = (res.stdout + res.stderr).strip()
            return (out[:3000] + "…[truncated]") if len(out) > 3000 else (out or "(no output)")
        except subprocess.TimeoutExpired:
            return "Command timed out"
        except Exception as e:
            return f"Command error: {e}"

    elif name == "browse_url":
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(args["url"], timeout=20_000)
                title = page.title()
                text  = page.inner_text("body")[:4000]
                browser.close()
            return f"Title: {title}\n\n{text}"
        except Exception as e:
            return f"Browse error: {e}"

    elif name == "copy_to_clipboard":
        pyperclip.copy(args["text"])
        return "Copied to clipboard"

    elif name == "open_app":
        subprocess.Popen(args["app"], shell=True)
        return f"Launched: {args['app']}"

    return f"Unknown tool: {name}"


# ── AGENT LOOP ────────────────────────────────────────────────────────────────
def _run_agent(messages: list, tool_logs: list, agent_mode: bool) -> str:
    if _llm is None:
        return "No model loaded. Please select a .gguf model from the sidebar."

    history = list(messages)

    for _ in range(25):  # max iterations
        kwargs: dict = {
            "messages":    history,
            "max_tokens":  1024,
            "temperature": 0.7,
        }
        if agent_mode:
            kwargs["tools"]       = TOOLS
            kwargs["tool_choice"] = "auto"

        response = _llm.create_chat_completion(**kwargs)
        msg = response["choices"][0]["message"]

        # Pure text reply — done
        if not msg.get("tool_calls"):
            return (msg.get("content") or "").strip()

        # Append assistant message (with tool calls)
        history.append(msg)

        for tc in msg["tool_calls"]:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except Exception:
                fn_args = {}

            detail_str = json.dumps(fn_args, ensure_ascii=False)

            # Ask permission for sensitive actions
            if fn_name in PERMISSION_REQUIRED:
                allowed = _ask_permission(fn_name, detail_str)
                if not allowed:
                    result = "User denied this action."
                    tool_logs.append({"action": fn_name, "detail": "denied by user"})
                else:
                    result = _run_tool(fn_name, fn_args)
                    tool_logs.append({"action": fn_name, "detail": detail_str[:100]})
            else:
                result = _run_tool(fn_name, fn_args)
                tool_logs.append({"action": fn_name, "detail": detail_str[:100]})

            history.append({
                "role":        "tool",
                "tool_call_id": tc["id"],
                "content":     str(result),
            })

    return "Reached maximum steps. The task may be incomplete."


# ── CHAT PERSISTENCE ──────────────────────────────────────────────────────────
def _chat_file(cid: str) -> Path:
    return CHATS_DIR / f"{cid}.json"

def _load(cid: str) -> dict:
    p = _chat_file(cid)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"id": cid, "title": "New Chat", "messages": [], "created": time.time()}

def _save(chat: dict) -> None:
    _chat_file(chat["id"]).write_text(
        json.dumps(chat, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── PYWEBVIEW API ─────────────────────────────────────────────────────────────
class TadiumAPI:

    # window controls
    def minimize(self):
        if _window: _window.minimize()

    def maximize(self):
        if _window:
            if getattr(_window, "maximized", False):
                _window.restore()
            else:
                _window.maximize()

    def close_app(self):
        if _window: _window.destroy()

    # permission callback — called by JS after user clicks Allow/Deny
    def _perm_answer(self, allowed: bool):
        global _perm_allowed
        _perm_allowed = bool(allowed)
        _perm_event.set()

    # model management
    def scan_models(self) -> list:
        out = []
        for f in sorted(MODELS_DIR.glob("*.gguf")):
            mb = f.stat().st_size / (1024 * 1024)
            size_str = f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.0f} MB"
            out.append({"path": str(f), "name": f.stem, "size": size_str})
        return out

    def load_model(self, path: str) -> dict:
        global _llm, _model_name
        try:
            _llm = Llama(
                model_path=path,
                n_ctx=8192,
                n_gpu_layers=-1,   # offload all layers to GPU if available
                verbose=False,
                chat_format="chatml",
            )
            _model_name = Path(path).stem
            return {"ok": True, "name": _model_name}
        except Exception as e:
            _llm = None
            return {"ok": False, "error": str(e)}

    # chat management
    def list_chats(self) -> list:
        chats = []
        for f in sorted(CHATS_DIR.glob("*.json"), key=lambda x: -x.stat().st_mtime):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                chats.append({"id": d["id"], "title": d.get("title", "Untitled")})
            except Exception:
                pass
        return chats

    def new_chat(self) -> dict:
        cid  = str(uuid.uuid4())[:8]
        chat = {"id": cid, "title": "New Chat", "messages": [], "created": time.time()}
        _save(chat)
        return {"id": cid}

    def get_chat(self, chat_id: str) -> dict:
        return _load(chat_id)

    # main message handler
    def send_message(self, payload: dict) -> dict:
        cid        = payload["chat_id"]
        user_msg   = payload["message"]
        agent_mode = payload.get("agent_mode", True)

        chat = _load(cid)

        # Auto-title on first message
        if not chat["messages"]:
            chat["title"] = user_msg[:45]

        # Build model history
        model_msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in chat["messages"]:
            model_msgs.append({"role": m["role"], "content": m["content"]})
        model_msgs.append({"role": "user", "content": user_msg})

        # Persist user turn
        chat["messages"].append({"role": "user", "content": user_msg, "ts": time.time()})

        # Run agent
        tool_logs: list = []
        reply = _run_agent(model_msgs, tool_logs, agent_mode)

        # Persist assistant turn
        chat["messages"].append({"role": "agent", "content": reply, "ts": time.time()})
        _save(chat)

        return {"reply": reply, "tool_logs": tool_logs}


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def main():
    global _window

    api = TadiumAPI()

    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)       # PyInstaller bundle
    else:
        base = Path(__file__).parent    # dev mode

    html = base / "index.html"

    _window = webview.create_window(
        title            = "Tadium",
        url              = str(html),
        js_api           = api,
        width            = 1120,
        height           = 740,
        min_size         = (820, 560),
        frameless        = True,
        easy_drag        = False,
        background_color = "#111110",
    )

    webview.start(debug=False)


if __name__ == "__main__":
    main()
