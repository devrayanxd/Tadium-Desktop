# 🤖 Tadium

**AI-powered Windows automation agent that runs locally with GGUF models.**

Tadium gives you a desktop app where you can ask an AI to control your PC: move the mouse, type text, run commands, browse the web, create files, and more — all with permission gating and zero cloud dependencies.

---

## ⚡ Quick Start

```cmd
pip install -r requirements.txt
playwright install chromium
build.bat
```

Then run `dist\Tadium\Tadium.exe` and load a `.gguf` model from `C:\Tadium\models\`.

📖 **Full instructions:** See [INSTRUCTIONS.md](INSTRUCTIONS.md)

---

## 🎯 Features

- 🧠 Local GGUF models (Llama, Phi, Qwen, etc.)
- 🖱️ Mouse & keyboard control
- 📂 File operations
- 💻 Command execution
- 🌐 Web browsing (headless)
- 📸 Screenshot capture
- 🔒 Permission system for every action
- 💬 Chat persistence

---

## 🛠️ Tech Stack

- **Python 3.11** + PyInstaller
- **llama-cpp-python** for GGUF inference
- **pywebview** for native window
- **pyautogui** for desktop automation
- **Playwright** for web browsing

---

## 📦 Distribution

The built EXE is ~300MB and includes everything except the GGUF model.  
Users must download their own model and place it in `C:\Tadium\models\`.

---

## ⚠️ Requirements

- Windows 10/11 (x64)
- Python 3.11
- 8GB+ RAM
- NVIDIA GPU optional (for faster inference)

---

## 📝 License

MIT License - see LICENSE file

---

## 🤝 Contributing

PRs welcome! Focus areas:
- macOS/Linux support
- Tool reliability improvements
- UI polish
- Model quantization guides

---

**Built by Admin01** | Powered by llama.cpp
