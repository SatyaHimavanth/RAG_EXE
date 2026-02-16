from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from dotenv import load_dotenv
load_dotenv()

from backend.api import router as api_router, settings, APP_DIR, BUNDLE_DIR
from backend.database import init_sqlite
import os
import socket


def validate_models():
    if not settings.CHAT_MODEL_PATH.exists():
        raise RuntimeError(
            f"Chat model not found: {settings.CHAT_MODEL_PATH}"
        )

    if not settings.CHAT_MODEL_FORMAT:
        raise RuntimeError(
            f"Chat model format not found: {settings.CHAT_MODEL_FORMAT}"
        )

    if not settings.EMBED_MODEL_PATH.exists():
        raise RuntimeError(
            f"Embedding model not found: {settings.EMBED_MODEL_PATH}"
        )


validate_models()

app = FastAPI(title="RAG Chatbot")

# Initialize Database
init_sqlite()

# Mount API Router
app.include_router(api_router, prefix="/api")

# Mount Static Files
STATIC_DIR = BUNDLE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def read_root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manage")
async def read_manage():
    return FileResponse(STATIC_DIR / "manage.html")


@app.get("/profile")
async def read_profile():
    return FileResponse(STATIC_DIR / "profile.html")


if __name__ == "__main__":
    import uvicorn

    HOST = os.getenv("HOST", "127.0.0.1")
    preferred_port = int(os.getenv("PORT", "8000"))

    def find_available_port(host: str, start_port: int, attempts: int = 20) -> int:
        for port in range(start_port, start_port + attempts):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if sock.connect_ex((host, port)) != 0:
                    return port
        return start_port

    PORT = find_available_port(HOST, preferred_port)
    URL = f"http://{HOST}:{PORT}"

    # Keep startup banner ASCII-safe for Windows consoles.
    print("\n" + "=" * 50)
    print("RAG Chatbot Server Starting...")
    if PORT != preferred_port:
        print(f"Port {preferred_port} is busy. Using {PORT} instead.")
    print(f"Visit: {URL}")
    print("=" * 50 + "\n")

    # Pass app object directly; string import is brittle in PyInstaller bundles.
    uvicorn.run(app, host=HOST, port=PORT, reload=False, log_level="info")
