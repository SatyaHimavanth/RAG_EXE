import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


def get_bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


APP_DIR = get_app_dir()
BUNDLE_DIR = get_bundle_dir()


load_dotenv(APP_DIR / ".env", override=False)


class Settings:
    SUMMARY_CHUNK_SIZE = int(os.getenv("SUMMARY_CHUNK_SIZE", 4000))

    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 2000))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 400))
    RETRIEVED_DOCS_COUNT = int(os.getenv("RETRIEVED_DOCS_COUNT", 3))
    
    # Model configs
    CHAT_MODEL_PATH = APP_DIR / "chat.nextgen"
    CHAT_MODEL_FORMAT = os.getenv("CHAT_MODEL_FORMAT", "qwen")
    N_CTX = int(os.getenv("N_CTX", 4096))
    N_GPU_LAYERS = int(os.getenv("N_GPU_LAYERS", -1))
    EMBED_MODEL_PATH = APP_DIR / "embed.nextgen"
    
settings = Settings()
