# TADIUM MVP - Setup & Build Instructions

## 🎯 Goal
Build a production-ready Windows EXE that runs Tadium with local GGUF models.

---

## 📋 Prerequisites

1. **Python 3.11** (NOT 3.12 or 3.14 — llama-cpp-python has best support on 3.11)
   - Download: https://www.python.org/downloads/release/python-3118/
   - During install: **Check "Add Python to PATH"**

2. **Git** (optional, for cloning from GitHub)

3. **Windows 10/11** (x64)

---

## 🚀 Quick Start (5 steps)

### Step 1: Get the code
```cmd
git clone https://github.com/devrayanxd/Tadium-Desktop.git
cd Tadium-Desktop
```

Or extract the ZIP if you downloaded manually.

---

### Step 2: Install dependencies
```cmd
pip install -r requirements.txt
```

**Important:** If you have a NVIDIA GPU and want GPU acceleration:
```cmd
pip uninstall llama-cpp-python -y
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121
```

This installs the CUDA-enabled version for faster inference.

---

### Step 3: Install Playwright browsers
```cmd
playwright install chromium
```

This downloads the headless browser for the `browse_url` tool.

---

### Step 4: Build the EXE
```cmd
build.bat
```

This runs PyInstaller and creates `dist\Tadium\Tadium.exe`.

The build takes 2-5 minutes. You'll see:
```
[1/5] Installing dependencies...
[2/5] Installing Playwright browsers...
[3/5] Cleaning old builds...
[4/5] Building EXE with PyInstaller...
[5/5] Build complete!
```

---

### Step 5: Add your model
1. Download a `.gguf` model (recommended: Llama 3.2 3B or Phi-3.5 Mini)
   - Hugging Face: https://huggingface.co/models?library=gguf
   
2. Create `C:\Tadium\models\` folder

3. Copy your `.gguf` file there (e.g., `C:\Tadium\models\llama-3.2-3b-instruct-Q4_K_M.gguf`)

---

## 🎮 Running Tadium

**Development mode:**
```cmd
python main.py
```

**Production EXE:**
```
dist\Tadium\Tadium.exe
```

**First launch:**
1. Click the model dropdown in the sidebar
2. Select your `.gguf` model
3. Wait for "Model loaded" status
4. Start chatting!

---

## 🛠️ Troubleshooting

### "Python not found"
- Reinstall Python 3.11 and check "Add to PATH"
- Close and reopen Command Prompt

### "pip not recognized"
```cmd
python -m ensurepip --upgrade
```

### "llama-cpp-python failed to install"
- Use Python 3.11 (not 3.12/3.14)
- If on Windows, install Visual Studio Build Tools:
  https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022

### "No module named 'llama_cpp'"
```cmd
pip install llama-cpp-python==0.3.4
```

### "playwright not found"
```cmd
pip install playwright==1.49.0
playwright install chromium
```

### EXE crashes on launch
- Check `C:\Tadium\models\` exists
- Try running `main.py` directly to see error logs

### Model won't load
- Verify the `.gguf` file is valid (not corrupted)
- Try a smaller model first (3B parameters)
- Check available RAM (8GB+ recommended)

### GPU not detected
Reinstall llama-cpp-python with CUDA:
```cmd
pip uninstall llama-cpp-python -y
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121
```

---

## 📦 Distribution

To share the EXE:
1. Zip the entire `dist\Tadium\` folder (300-500 MB)
2. Share with users
3. Users extract and run `Tadium.exe`
4. Users must add their own `.gguf` model to `C:\Tadium\models\`

**Note:** The EXE bundles everything except the GGUF model (those are too large).

---

## 🔥 Features

✅ Local GGUF model execution (CPU/GPU)  
✅ Permission gating for every action  
✅ Mouse & keyboard control  
✅ File operations (read/write/delete)  
✅ Command execution  
✅ Web browsing (Playwright)  
✅ Screenshot capture  
✅ Clipboard operations  
✅ Chat persistence  

---

## 📝 Model Recommendations

| Model | Size | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| Llama 3.2 1B | 1GB | ⚡⚡⚡ | ⭐⭐ | Testing |
| Llama 3.2 3B | 2GB | ⚡⚡ | ⭐⭐⭐ | Balanced |
| Phi-3.5 Mini | 2.5GB | ⚡⚡ | ⭐⭐⭐⭐ | Recommended |
| Qwen 2.5 7B | 4GB | ⚡ | ⭐⭐⭐⭐⭐ | Best quality |

Download from Hugging Face and look for quantized versions (Q4_K_M is a good balance).

---

## 🎨 Optional: Icon Conversion

If you want a custom icon:
1. Convert `icon.png` to `icon.ico` using an online tool
2. Uncomment the `icon='icon.ico'` line in `tadium.spec`
3. Rebuild

---

## ⚠️ Known Limitations

- Screenshot resolution is halved to save memory
- Browser tool is headless only (no visible browser window)
- Max 25 agent loop iterations per task
- First launch is slow (loads model into VRAM)

---

## 📧 Support

If you hit issues building:
1. Check this guide again
2. Make sure Python 3.11 is installed
3. Try deleting `build/` and `dist/` folders and rebuilding

---

**Build timestamp:** Generated for MVP release  
**Target platform:** Windows 10/11 (x64)  
**Python version:** 3.11.x
