from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from dotenv import load_dotenv
load_dotenv()

from backend.api import router as api_router, settings, APP_DIR, BUNDLE_DIR
from backend.database import init_sqlite
import os

def validate_models():
    # print(settings.CHAT_MODEL_PATH)
    # print(settings.CHAT_MODEL_FORMAT)
    # print(settings.EMBED_MODEL_PATH)
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
# We serve 'static' directory at '/static' for assets (js, css)
# And we will have a separate route for '/' to serve index.html
STATIC_DIR = BUNDLE_DIR / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def read_root():
    return FileResponse(STATIC_DIR / 'index.html')

@app.get("/manage")
async def read_manage():
    return FileResponse(STATIC_DIR / 'manage.html')

@app.get("/profile")
async def read_profile():
    return FileResponse('static/profile.html')

if __name__ == "__main__":
    import uvicorn
    
    HOST = "localhost"
    PORT = 8000
    URL = f"http://{HOST}:{PORT}"
    
    # Print colored startup message
    print("\n" + "=" * 50)
    print(f"\033[92m✓ RAG Chatbot Server Starting...\033[0m")
    print(f"\033[94m➜ Visit: \033[4m{URL}\033[0m")
    print("=" * 50 + "\n")
    
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)