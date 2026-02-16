import sqlite3
import chromadb
from chromadb.config import Settings
import os
from backend.logger import setup_logger
from backend.config import APP_DIR


logger = setup_logger(__name__)

# SQLite Setup
DB_PATH = APP_DIR  / "chat_history.db"

def init_sqlite():
    logger.info(f"Initializing SQLite DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            is_archived BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Migration
    try:
        c.execute("ALTER TABLE sessions ADD COLUMN is_archived BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass 
        
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_name TEXT,
            filename TEXT,
            summary TEXT,
            upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            type TEXT, -- info, success, error
            task_id TEXT, -- UUID for tracking related background tasks
            progress INTEGER DEFAULT 0, -- percent 0-100
            status TEXT, -- processing, completed, failed
            is_read BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    # Cleanup stale 'processing' tasks from previous runs (app was closed during task)
    c.execute("SELECT task_id, message FROM notifications WHERE status = 'processing'")
    stale_tasks = c.fetchall()
    
    if stale_tasks:
        for task_id, message in stale_tasks:
            # Extract filename from message like "Summarization started for filename.pdf"
            if "started for " in message:
                filename = message.split("started for ")[-1]
                c.execute("UPDATE documents SET summary = 'Upload cancelled' WHERE summary = 'Summary generation in progress...' AND filename = ?", (filename,))
        
        c.execute("UPDATE notifications SET status = 'failed', message = message || ' (interrupted)' WHERE status = 'processing'")
        logger.info(f"Marked {len(stale_tasks)} stale 'processing' notifications as 'failed'")
    conn.commit()

    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

# ChromaDB Setup
CHROMA_PATH = APP_DIR / "chroma_db"
logger.info(f"Initializing ChromaDB: {CHROMA_PATH}")
settings = Settings(anonymized_telemetry=False)
chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH), settings=settings)

def get_chroma_client():
    return chroma_client
