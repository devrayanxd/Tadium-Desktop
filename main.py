import os
import sys
import json
import time
import base64
import threading
import subprocess
import webview
import re
from io import BytesIO
from typing import Optional, Callable

import mss
import mss.tools
import pyautogui
from PIL import Image
import requests
from pynput import keyboard


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

MODEL_DIR = os.path.join("C:", "Tadium", "models")
OLLAMA_BASE = "http://localhost:11434"

_vision_cache = {}


SYSTEM_PROMPT = """You are Tadium, an AI agent that controls a computer via mouse and keyboard actions.
You respond with JSON only. Your response must be a valid JSON object with this structure:
{
    "thought": "Brief reasoning about what to do next",
    "action": "one of: click, type, hotkey, scroll, wait, screenshot, done",
    "params": {},
    "done": false
}

Actions and their params:
- click: {"x": int, "y": int, "button": "left"|"right"}
- type: {"text": "string to type"}
- hotkey: {"keys": ["key1", "key2"]} (e.g., ["ctrl", "c"])
- scroll: {"x": int, "y": int, "clicks": int}
- wait: {"seconds": float}
- screenshot: {}
- done: {}

Always keep thoughts concise. Be precise with coordinates. Respond in JSON only, no markdown, no code blocks."""

BLOCKED_COMMANDS = [
    "rm -rf", "rm -r", "del /f", "del /s", "format", "system32",
    "shutdown /r", "shutdown -r", "shutdown /s", "shutdown -s",
    "mkfs", "fdisk", "diskpart", "reg delete", "powershell remove",
    "chmod 777", "sudo rm", "rmdir /s", ":(){ :|:& };",
    "wget.*\\|.*sh", "curl.*\\|.*sh", "base64.*decode", "eval(", "exec(", "__import__",
]

MODELS = {
    "ollama_llama3.2-vision": {
        "name": "Llama 3.2 Vision", "size": "~2.7 GB", "tag": "llama3.2-vision",
        "type": "local", "light": False, "description": "Standard vision model, good balance of speed and accuracy",
    },
    "ollama_moondream": {
        "name": "Moondream 2", "size": "~800 MB", "tag": "moondream",
        "type": "local", "light": True, "description": "Lightweight vision model for lower-end machines",
    },
    "ollama_llava-phi3": {
        "name": "LLaVA Phi-3", "size": "~2.3 GB", "tag": "llava-phi3",
        "type": "local", "light": True, "description": "Fast lightweight model, good for quick tasks",
    },
    "openai_gpt-4o": {
        "name": "GPT-4o", "size": "Cloud", "tag": None,
        "type": "cloud", "light": False, "description": "OpenAI's flagship model, requires API key",
    },
    "anthropic_claude-3.5": {
        "name": "Claude 3.5 Sonnet", "size": "Cloud", "tag": None,
        "type": "cloud", "light": False, "description": "Anthropic's advanced model, requires API key",
    },
}


# === SAFETY ===

def is_blocked(action: str) -> tuple[bool, str]:
    action_lower = action.lower()
    for pattern in BLOCKED_COMMANDS:
        if re.search(pattern, action_lower):
            return True, f"Action blocked: '{action}' matches blocked pattern '{pattern}'"
    dangerous_paths = [r"c:\\windows", r"c:\\program files", r"/etc/passwd", r"/etc/shadow", r"/var/log"]
    for path in dangerous_paths:
        if re.search(path, action_lower):
            return True, f"Action blocked: accesses protected path '{path}'"
    return False, ""


# === AI AGENT ===

def _ollama_supports_vision(model: str) -> bool:
    if model in _vision_cache:
        return _vision_cache[model]
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/show", json={"name": model}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            details = data.get("details", {})
            family = details.get("family", "").lower()
            families = details.get("families", [])
            families_lower = [f.lower() for f in families]
            vision_indicators = ["clip", "llava", "vision", "moondream", "qwen2vl", "bunny", "minicpm"]
            for indicator in vision_indicators:
                if indicator in family or any(indicator in f for f in families_lower):
                    _vision_cache[model] = True
                    return True
            projector = data.get("model_info", {})
            if any("vision" in k.lower() or "clip" in k.lower() or "projector" in k.lower() for k in projector):
                _vision_cache[model] = True
                return True
            _vision_cache[model] = False
            return False
    except Exception:
        pass
    known_vision = ["llama3.2-vision", "moondream", "moondream2", "llava", "llava-phi3", "llava-llama3", "llava-llama3.1", "bakllava", "vision", "qwen2-vl", "qwen2.5-vl"]
    is_v = any(vm in model.lower() for vm in known_vision)
    _vision_cache[model] = is_v
    return is_v


def _parse_json_response(content: str) -> dict:
    content = content.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                pass
    return {
        "thought": "Failed to parse AI response",
        "action": "wait",
        "params": {"seconds": 1},
        "done": False,
        "error": f"Could not parse response: {content[:300]}",
    }


def process_step(instruction: str, screenshot_b64: str, model: str = "llama3.2-vision", api_key: Optional[str] = None, history: Optional[list] = None) -> dict:
    if history is None:
        history = []
    if model.startswith("ollama"):
        model_name = model.replace("ollama_", "") or "llama3.2-vision"
        return _call_ollama(instruction, screenshot_b64, model_name, history)
    elif model.startswith("openai"):
        return _call_openai(instruction, screenshot_b64, api_key, history)
    elif model.startswith("anthropic"):
        return _call_anthropic(instruction, screenshot_b64, api_key, history)
    return _call_ollama(instruction, screenshot_b64, model, history)


def _call_ollama(instruction: str, screenshot_b64: str, model: str, history: list) -> dict:
    url = f"{OLLAMA_BASE}/api/chat"
    supports_vision = _ollama_supports_vision(model)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for entry in history:
        messages.append({"role": entry["role"], "content": entry["content"]})
    user_message = {"role": "user", "content": f"User instruction: {instruction}"}
    if supports_vision:
        user_message["images"] = [screenshot_b64]
    messages.append(user_message)
    payload = {
        "model": model, "messages": messages, "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
    }
    if supports_vision:
        payload["format"] = "json"
    try:
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
        result = response.json()
        content = result["message"]["content"]
        parsed = _parse_json_response(content)
        if parsed.get("error") and "cannot read" in parsed["error"].lower():
            return _retry_without_image(instruction, model, history)
        return parsed
    except requests.exceptions.ConnectionError:
        return {"thought": "Cannot connect to Ollama", "action": "done", "params": {}, "done": True, "error": "Ollama is not running. Start Ollama with 'ollama serve'."}
    except requests.exceptions.HTTPError as e:
        error_text = e.response.text if hasattr(e, "response") else str(e)
        if "does not support image" in error_text.lower() or "cannot read" in error_text.lower():
            return _retry_without_image(instruction, model, history)
        return {"thought": "Ollama API error", "action": "done", "params": {}, "done": True, "error": f"Ollama returned {e.response.status_code}: {error_text[:300]}"}
    except Exception as e:
        return {"thought": "Unexpected error", "action": "done", "params": {}, "done": True, "error": str(e)}


def _retry_without_image(instruction: str, model: str, history: list) -> dict:
    url = f"{OLLAMA_BASE}/api/chat"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for entry in history:
        messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": f"User instruction: {instruction}. You cannot see the screen right now, do your best based on the instruction."})
    payload = {"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.1, "num_predict": 512}, "format": "json"}
    try:
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
        result = response.json()
        parsed = _parse_json_response(result["message"]["content"])
        parsed["thought"] = "[No vision] " + parsed.get("thought", "")
        return parsed
    except Exception as e:
        return {"thought": "Retry failed", "action": "done", "params": {}, "done": True, "error": f"Model does not support vision. Use a vision model like llama3.2-vision or moondream. Error: {str(e)}"}


def _call_openai(instruction: str, screenshot_b64: str, api_key: Optional[str], history: list) -> dict:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": [{"type": "text", "text": f"Instruction: {instruction}"}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}", "detail": "high"}}]})
    payload = {"model": "gpt-4o", "messages": messages, "max_tokens": 500, "temperature": 0.1}
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    return _parse_json_response(response.json()["choices"][0]["message"]["content"])


def _call_anthropic(instruction: str, screenshot_b64: str, api_key: Optional[str], history: list) -> dict:
    headers = {"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"}
    messages = [{"role": entry["role"], "content": entry["content"]} for entry in history]
    messages.append({"role": "user", "content": [{"type": "text", "text": f"Instruction: {instruction}"}, {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}}]})
    payload = {"model": "claude-3-5-sonnet-20241022", "max_tokens": 1024, "system": SYSTEM_PROMPT, "messages": messages}
    response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    return _parse_json_response(response.json()["content"][0]["text"])


# === ENGINE ===

class ExecutionEngine:
    def __init__(self):
        self._running = False
        self._stop_event = threading.Event()
        self._esc_count = 0
        self._esc_lock = threading.Lock()
        self._listener = None
        self._on_status: Optional[Callable] = None
        self._on_step: Optional[Callable] = None

    def set_callbacks(self, on_status: Callable, on_step: Callable):
        self._on_status = on_status
        self._on_step = on_step

    def capture_screen(self) -> str:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
            buffer = BytesIO()
            img.save(buffer, format="PNG", optimize=True, quality=85)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def start_esc_listener(self):
        def on_press(key):
            if not self._running:
                return
            if key == keyboard.Key.esc:
                with self._esc_lock:
                    self._esc_count += 1
                    if self._esc_count >= 2:
                        self._emit_status("STOPPED: Double ESC detected")
                        self.stop()

        self._listener = keyboard.Listener(on_press=on_press, on_release=lambda k: None)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        self._running = False
        self._stop_event.set()
        if self._listener:
            self._listener.stop()
            self._listener = None

    def execute_action(self, action: str, params: dict) -> tuple[bool, str]:
        blocked, reason = is_blocked(str(params))
        if blocked:
            return False, reason
        try:
            if action == "click":
                pyautogui.click(x=params.get("x", 0) * 2, y=params.get("y", 0) * 2, button=params.get("button", "left"))
                return True, f"Clicked at ({params.get('x', 0)}, {params.get('y', 0)})"
            elif action == "type":
                pyautogui.typewrite(params.get("text", ""), interval=0.02)
                return True, f"Typed: {params.get('text', '')[:50]}..."
            elif action == "hotkey":
                pyautogui.hotkey(*params.get("keys", []))
                return True, f"Pressed hotkey: {params.get('keys', [])}"
            elif action == "scroll":
                pyautogui.moveTo(params.get("x", 0) * 2, params.get("y", 0) * 2)
                pyautogui.scroll(params.get("clicks", 0))
                return True, f"Scrolled {params.get('clicks', 0)} clicks"
            elif action == "wait":
                time.sleep(params.get("seconds", 1))
                return True, f"Waited {params.get('seconds', 1)}s"
            elif action == "screenshot":
                return True, "Screenshot captured"
            elif action == "done":
                return True, "Task completed"
            return False, f"Unknown action: {action}"
        except Exception as e:
            return False, f"Execution error: {str(e)}"

    def run_loop(self, instruction: str, model: str, api_key: Optional[str], agent_process_step: Callable, max_steps: int = 20):
        self._running = True
        self._stop_event.clear()
        self._esc_count = 0
        model_name = model.replace("ollama_", "").replace("openai_", "").replace("anthropic_", "")
        self._emit_status(f"Starting with model: {model_name}")
        history = []
        for step in range(1, max_steps + 1):
            if not self._running:
                self._emit_status("Stopped by user")
                break
            self._emit_status(f"Step {step}/{max_steps}: Capturing screen...")
            try:
                screenshot_b64 = self.capture_screen()
            except Exception as e:
                self._emit_status(f"Screenshot error: {str(e)}")
                break
            self._emit_status(f"Step {step}/{max_steps}: Thinking...")
            try:
                result = agent_process_step(instruction=instruction, screenshot_b64=screenshot_b64, model=model, api_key=api_key, history=history)
                if "error" in result:
                    self._emit_status(f"AI response error: {result.get('error', 'Unknown')}")
                    break
            except Exception as e:
                self._emit_status(f"AI error: {str(e)}")
                break
            action = result.get("action", "wait")
            params = result.get("params", {})
            thought = result.get("thought", "")
            done = result.get("done", False)
            self._emit_step(step, thought, action, params)
            if done:
                self._emit_status("Task completed successfully")
                break
            history.append({"role": "assistant", "content": json.dumps(result)})
            history.append({"role": "user", "content": "Action executed. Screenshot attached."})
            if action != "screenshot":
                self._emit_status(f"Step {step}/{max_steps}: Executing {action}...")
                success, message = self.execute_action(action, params)
                if not success:
                    self._emit_status(f"Action failed: {message}")
                    history.append({"role": "user", "content": f"Action failed: {message}"})
                else:
                    self._emit_status(f"Action done: {message}")
            else:
                self._emit_status("Screenshot taken, analyzing...")
            if not self._running:
                break
        self._running = False
        self._emit_status("Loop finished")

    def _emit_status(self, message: str):
        if self._on_status:
            self._on_status(message)

    def _emit_step(self, step: int, thought: str, action: str, params: dict):
        if self._on_step:
            self._on_step(step, thought, action, params)

    @property
    def is_running(self) -> bool:
        return self._running


# === MODEL MANAGER ===

class ModelManager:
    def __init__(self):
        os.makedirs(MODEL_DIR, exist_ok=True)

    def get_models(self) -> list[dict]:
        installed = self._get_installed_models()
        result = []
        for key, info in MODELS.items():
            entry = info.copy()
            entry["key"] = key
            entry["installed"] = info["tag"] is None or info["tag"] in installed
            entry["local_path"] = os.path.join(MODEL_DIR, info["tag"]) if info["tag"] else None
            result.append(entry)
        return result

    def is_ollama_running(self) -> bool:
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def download_model(self, model_tag: str, on_progress: Optional[Callable] = None, on_complete: Optional[Callable] = None):
        def _download():
            model_dir = os.path.join(MODEL_DIR, model_tag)
            os.makedirs(model_dir, exist_ok=True)
            if on_progress:
                on_progress({"status": "downloading", "percent": 0, "message": f"Downloading {model_tag}..."})
            try:
                proc = subprocess.Popen(["ollama", "pull", model_tag], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                while True:
                    line = proc.stdout.readline()
                    if not line and proc.poll() is not None:
                        break
                    if not line:
                        continue
                    try:
                        data = json.loads(line.strip())
                        status = data.get("status", "")
                        if "completed" in data and "total" in data and data["total"] > 0:
                            pct = int((data["completed"] / data["total"]) * 100)
                            downloaded_mb = data["completed"] / (1024 * 1024)
                            total_mb = data["total"] / (1024 * 1024)
                            if on_progress:
                                on_progress({"status": "downloading", "percent": pct, "message": f"Downloading... {pct}% ({downloaded_mb:.0f}/{total_mb:.0f} MB)"})
                        elif "pulling" in status or "downloading" in status.lower():
                            if on_progress:
                                on_progress({"status": "downloading", "percent": 0, "message": status})
                    except json.JSONDecodeError:
                        if line.strip() and on_progress:
                            on_progress({"status": "downloading", "percent": 0, "message": line.strip()[:120]})
                return_code = proc.wait()
                if return_code == 0:
                    marker = os.path.join(model_dir, ".installed")
                    with open(marker, "w") as f:
                        f.write("installed")
                    if on_progress:
                        on_progress({"status": "complete", "percent": 100, "message": f"{model_tag} installed to C:\\Tadium\\models\\{model_tag}"})
                    if on_complete:
                        on_complete(model_tag, True, model_dir)
                else:
                    if on_progress:
                        on_progress({"status": "error", "percent": 0, "message": f"Download failed (exit code {return_code})"})
                    if on_complete:
                        on_complete(model_tag, False, None)
            except Exception as e:
                if on_progress:
                    on_progress({"status": "error", "percent": 0, "message": f"Error: {str(e)}"})
                if on_complete:
                    on_complete(model_tag, False, None)
        threading.Thread(target=_download, daemon=True).start()

    def _get_installed_models(self) -> list[str]:
        installed = []
        if self.is_ollama_running():
            try:
                resp = requests.get("http://localhost:11434/api/tags", timeout=5)
                if resp.status_code == 200:
                    for model in resp.json().get("models", []):
                        name = model["name"].split(":")[0]
                        installed.append(name)
                        installed.append(name.split("/")[-1])
            except Exception:
                pass
        if os.path.exists(MODEL_DIR):
            for item in os.listdir(MODEL_DIR):
                item_path = os.path.join(MODEL_DIR, item)
                if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, ".installed")) and item not in installed:
                    installed.append(item)
        return list(set(installed))

    def uninstall_model(self, model_tag: str) -> tuple[bool, str]:
        try:
            subprocess.run(["ollama", "rm", model_tag], capture_output=True, text=True, timeout=30)
        except Exception:
            pass
        model_dir = os.path.join(MODEL_DIR, model_tag)
        if os.path.exists(model_dir):
            try:
                import shutil
                shutil.rmtree(model_dir)
            except Exception:
                pass
        return True, f"Removed {model_tag}"


# === MAIN ===

engine = ExecutionEngine()
model_mgr = ModelManager()


class Api:
    def on_status(self, message):
        try:
            escaped = message.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "").replace('"', '\\"')
            window.evaluate_js(f"window.pywebview.api.on_status('{escaped}')")
        except Exception:
            pass

    def on_step(self, step, thought, action, params):
        try:
            thought = thought.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "").replace('"', '\\"')
            action = action.replace("\\", "\\\\").replace("'", "\\'").replace("\r", "").replace('"', '\\"')
            params_str = json.dumps(params).replace("'", "\\'").replace('"', '\\"')
            window.evaluate_js(f"window.pywebview.api.on_step({step}, '{thought}', '{action}', JSON.parse('{params_str}'))")
        except Exception:
            pass

    def get_models(self):
        return model_mgr.get_models()

    def download_model(self, model_tag, on_progress_cb=None, on_complete_cb=None):
        def js_progress(update):
            try:
                window.evaluate_js(f"({on_progress_cb})({json.dumps(update)})")
            except Exception:
                pass
        def js_complete(tag, success, path):
            try:
                path_str = str(path).replace("\\", "\\\\") if path else ""
                window.evaluate_js(f"({on_complete_cb})('{tag}', {success}, '{path_str}')")
            except Exception:
                pass
        model_mgr.download_model(model_tag, on_progress=js_progress, on_complete=js_complete)
        return {"success": True}

    def start_agent(self, instruction, model, max_steps=20):
        if engine.is_running:
            return {"success": False, "message": "Agent is already running"}
        api_key = None
        if model.startswith("openai"):
            api_key = os.environ.get("OPENAI_API_KEY", "")
        elif model.startswith("anthropic"):
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        threading.Thread(target=engine.run_loop, args=(instruction, model, api_key, process_step, max_steps), daemon=True).start()
        return {"success": True, "message": "Agent started"}

    def stop_agent(self):
        engine.stop()
        return {"success": True, "message": "Stop signal sent"}


def get_resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


if __name__ == "__main__":
    api = Api()
    engine.set_callbacks(on_status=api.on_status, on_step=api.on_step)
    engine.start_esc_listener()

    html_path = get_resource_path("index.html")
    if not os.path.exists(html_path):
        html_path = os.path.join(os.getcwd(), "index.html")

    url = f"file:///{html_path.replace(os.sep, '/')}"

    icon_path = get_resource_path("logo.png")
    if not os.path.exists(icon_path):
        icon_path = None

    window = webview.create_window(
        "Tadium AI Agent",
        url=url,
        js_api=api,
        width=1200,
        height=750,
        min_size=(960, 640),
        background_color="#09090b",
        text_select=False,
        icon=icon_path,
    )

    webview.start(debug=False)
