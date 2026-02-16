import os
import sys
import ctypes
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


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_env_explicit(name: str) -> bool:
    return name in os.environ and os.environ[name].strip() != ""


def _detect_memory_bytes() -> tuple[int, int]:
    # Returns (total_bytes, available_bytes)
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return int(stat.ullTotalPhys), int(stat.ullAvailPhys)

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        total_pages = os.sysconf("SC_PHYS_PAGES")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        return int(page_size * total_pages), int(page_size * avail_pages)
    except Exception:
        return 0, 0


def _detect_profile() -> dict:
    total_mem, avail_mem = _detect_memory_bytes()
    total_gb = total_mem / (1024 ** 3) if total_mem else 0.0
    avail_gb = avail_mem / (1024 ** 3) if avail_mem else 0.0
    logical_cores = os.cpu_count() or 4

    # Thread cap keeps laptops responsive and avoids CPU oversubscription.
    n_threads = max(2, min(logical_cores - 1, 8))
    if avail_gb <= 4:
        return {
            "tier": "low",
            "n_ctx": 2048,
            "chat_max_tokens": 256,
            "summary_chunk_size": 1600,
            "summary_max_chunks": 8,
            "n_batch": 64,
            "n_threads": n_threads,
            "suggested_quant": "Q3_K_M to Q4_K_M",
            "total_ram_gb": round(total_gb, 2),
            "avail_ram_gb": round(avail_gb, 2),
            "logical_cores": logical_cores,
        }
    if avail_gb <= 8:
        return {
            "tier": "balanced",
            "n_ctx": 3072,
            "chat_max_tokens": 384,
            "summary_chunk_size": 2000,
            "summary_max_chunks": 10,
            "n_batch": 128,
            "n_threads": n_threads,
            "suggested_quant": "Q4_K_M",
            "total_ram_gb": round(total_gb, 2),
            "avail_ram_gb": round(avail_gb, 2),
            "logical_cores": logical_cores,
        }
    if avail_gb <= 12:
        return {
            "tier": "high",
            "n_ctx": 4096,
            "chat_max_tokens": 512,
            "summary_chunk_size": 2400,
            "summary_max_chunks": 12,
            "n_batch": 256,
            "n_threads": n_threads,
            "suggested_quant": "Q4_K_M to Q5_K_M",
            "total_ram_gb": round(total_gb, 2),
            "avail_ram_gb": round(avail_gb, 2),
            "logical_cores": logical_cores,
        }
    return {
        "tier": "very_high",
        "n_ctx": 6144,
        "chat_max_tokens": 768,
        "summary_chunk_size": 2800,
        "summary_max_chunks": 14,
        "n_batch": 256,
        "n_threads": n_threads,
        "suggested_quant": "Q5_K_M to Q6_K",
        "total_ram_gb": round(total_gb, 2),
        "avail_ram_gb": round(avail_gb, 2),
        "logical_cores": logical_cores,
    }


def _resolve_model_path(filename: str, app_dir: Path) -> Path:
    # 1) Preferred: next to the executable/script.
    primary = app_dir / filename
    if primary.exists():
        return primary

    # 2) Helpful fallback for local dev/testing: parent of dist folder.
    fallback = app_dir.parent / filename
    if fallback.exists():
        return fallback

    return primary


class Settings:
    def __init__(self):
        self.AUTO_PROFILE = _to_bool(os.getenv("AUTO_PROFILE"), True)
        self.AUTO_PROFILE_STRICT = _to_bool(os.getenv("AUTO_PROFILE_STRICT"), True)
        self.PROFILE = _detect_profile() if self.AUTO_PROFILE else {}

        self.CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 2000))
        self.CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 400))
        self.RETRIEVED_DOCS_COUNT = int(os.getenv("RETRIEVED_DOCS_COUNT", 3))

        # Model paths
        self.CHAT_MODEL_PATH = _resolve_model_path("chat.nextgen", APP_DIR)
        self.EMBED_MODEL_PATH = _resolve_model_path("embed.nextgen", APP_DIR)
        self.CHAT_MODEL_FORMAT = os.getenv("CHAT_MODEL_FORMAT", "qwen")

        # Generation tuning
        self.N_GPU_LAYERS = int(os.getenv("N_GPU_LAYERS", -1))
        self.CHAT_TEMPERATURE = float(os.getenv("CHAT_TEMPERATURE", 0.3))
        self.CHAT_PRESENCE_PENALTY = float(os.getenv("CHAT_PRESENCE_PENALTY", 0.9))
        self.CHAT_REPEAT_PENALTY = float(os.getenv("CHAT_REPEAT_PENALTY", 1.1))

        # Runtime params (can be auto-profiled)
        self.N_CTX = self._resolve_int("N_CTX", 4096, "n_ctx")
        self.CHAT_MAX_TOKENS = self._resolve_int("CHAT_MAX_TOKENS", 512, "chat_max_tokens")
        self.SUMMARY_CHUNK_SIZE = self._resolve_int("SUMMARY_CHUNK_SIZE", 4000, "summary_chunk_size")
        self.SUMMARY_MAX_CHUNKS = self._resolve_int("SUMMARY_MAX_CHUNKS", 12, "summary_max_chunks")
        self.N_BATCH = self._resolve_int("N_BATCH", 256, "n_batch")
        self.N_THREADS = self._resolve_int("N_THREADS", max((os.cpu_count() or 4) - 1, 2), "n_threads")

        self.PROFILE_SUGGESTED_QUANT = self.PROFILE.get("suggested_quant", "Q4_K_M")

    def _resolve_int(self, env_name: str, default: int, profile_key: str) -> int:
        if not self.AUTO_PROFILE:
            return int(os.getenv(env_name, default))
        if self.AUTO_PROFILE_STRICT:
            return int(self.PROFILE.get(profile_key, int(os.getenv(env_name, default))))
        if _is_env_explicit(env_name):
            return int(os.getenv(env_name, default))
        return int(self.PROFILE.get(profile_key, int(os.getenv(env_name, default))))
    
settings = Settings()
