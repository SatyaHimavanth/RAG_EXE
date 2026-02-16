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


