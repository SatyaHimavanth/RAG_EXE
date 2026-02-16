## Extract and save the chroma zip at `C:\Users\<user>\.cache\` or use below command (not necessary)
```bash
New-Item -ItemType Directory -Force "$env:USERPROFILE\.cache" | Out-Null
Expand-Archive chroma.zip "$env:USERPROFILE\.cache"
```

## create virtual environment
```bash
python3 -m venv .uv_venv
```

## Activate virtual environment
```bash
.uv_venv\Scripts\activate
```

## Install uv
```bash
pip install uv
```

## Install Required packages
```bash
uv sync
```

## Install llama-cpp

### using pre-built wheel
```bash
uv pip install llama-cpp-python --find-links ./wheels/ --no-index
```

### Official pre-built wheels - NO compiler needed!
```bash
uv pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

### No-compiler safe install (Windows CPU, PyInstaller-friendly)
```bash
uv pip install --upgrade --only-binary=:all: "llama-cpp-python==0.3.2" --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

- `--only-binary=:all:` ensures pip/uv will not try to compile from source.
- If no matching wheel is found for your Python/CPU, installation fails fast instead of requiring C++ build tools.


## Run the app
```bash
uv run main.py
```


## Install gguf models (chat and embedding) and place them in `models` folder
```bash
Embedding Model: nomic-embed-text-v1.5.Q8_0.gguf
Chat Model: qwen2.5-0.5b-instruct-q8_0.gguf
```

- Note: make sure you download the models which are supported by latest llama-cpp version

## Qwen3 compatibility notes

- In a strict no-compiler Windows setup, available CPU wheels can be limited (often `0.3.2`).
- Qwen3 GGUF may fail on these older wheels even if Qwen2.5 works.
- This app exposes runtime compatibility at `GET /api/runtime/profile` and in the Profile page.
- If `qwen3_supported=false`, use one of:
  - `Qwen2.5-3B-Instruct` (`Q4_K_M` or `Q5_K_M`)
  - `Qwen2.5-1.5B-Instruct` (`Q4_K_M`)
  - `Qwen2.5-0.5B-Instruct` (`Q8_0` or `Q4_K_M`)

## Recommended model choices for 16GB RAM laptops (CPU)

- Best balance: `Qwen2.5-3B-Instruct` + `Q4_K_M`
- Faster/lighter: `Qwen2.5-1.5B-Instruct` + `Q4_K_M`
- Very low memory: `Qwen2.5-0.5B-Instruct` + `Q8_0`
- Embedding: `nomic-embed-text-v1.5` GGUF
