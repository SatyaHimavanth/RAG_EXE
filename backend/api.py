from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Body
from fastapi.responses import StreamingResponse
from typing import List, Generator
import shutil
import os
import sys
import uuid
import time
import json
import sqlite3
import asyncio
import re
from datetime import datetime

from backend.models import ChatRequest, ChatResponse, CollectionCreate, CollectionInfo, DocInfo, ChatMessage
from backend.database import get_chroma_client, get_db_connection
from backend.rag_engine import chat_stream, get_embedding, settings, APP_DIR, BUNDLE_DIR
from backend.ingest import load_document, split_text
from backend.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


def _version_tuple(raw_version: str) -> tuple:
    if not raw_version:
        return (0, 0, 0)
    core = raw_version.split("+", 1)[0]
    parts = re.findall(r"\d+", core)
    nums = [int(p) for p in parts[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)

# --- Chat Endpoints ---

@router.post("/chat")
async def chat(request: ChatRequest):
    logger.info(f"Chat request received. Session: {request.session_id}, Collection: {request.collection_name}")
    conn = get_db_connection()
    c = conn.cursor()
    
    if request.session_id:
        user_msg = request.messages[-1]
        c.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", 
                  (request.session_id, user_msg.role, user_msg.content))
        
        c.execute("SELECT title FROM sessions WHERE id = ?", (request.session_id,))
        row = c.fetchone()
        if row and row[0] == "New Chat":
            new_title = user_msg.content[:50] + "..." if len(user_msg.content) > 50 else user_msg.content
            c.execute("UPDATE sessions SET title = ? WHERE id = ?", (new_title, request.session_id))
            logger.info(f"Renamed session {request.session_id} to {new_title}")
            
        conn.commit()
    conn.close()

    async def response_generator():
        full_response = ""
        stream = chat_stream(request.messages, request.collection_name)

        for chunk in stream:
            full_response += chunk
            yield chunk
            await asyncio.sleep(0)
                  
        if request.session_id:
            clean_response = full_response.split("\n\n[METRICS]", 1)[0].strip()
            conn2 = get_db_connection()
            c2 = conn2.cursor()
            if clean_response:
                c2.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", 
                          (request.session_id, "assistant", clean_response))
                conn2.commit()
            conn2.close()
            logger.info("Bot response saved to DB")

    return StreamingResponse(response_generator(), media_type="text/plain")

@router.get("/history")
async def get_history(search: str = None):
    logger.info(f"Fetching history. Search: {search}")
    conn = get_db_connection()
    c = conn.cursor()
    
    query = "SELECT id, title, created_at FROM sessions WHERE is_archived = 0"
    params = []
    
    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")
        
    query += " ORDER BY created_at DESC"
    
    c.execute(query, tuple(params))
    sessions = c.fetchall()
    conn.close()
    return [{"id": s[0], "title": s[1], "created_at": s[2]} for s in sessions]

@router.get("/history/{session_id}")
async def get_session_history(session_id: int):
    logger.info(f"Fetching session history: {session_id}")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
    messages = c.fetchall()
    conn.close()
    return [{"role": m[0], "content": m[1]} for m in messages]

@router.post("/sessions")
async def create_session(title: str = "New Chat"):
    logger.info(f"Creating new session: {title}")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO sessions (title) VALUES (?)", (title,))
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": session_id, "title": title}

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int):
    logger.info(f"Deleting session: {session_id}")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@router.patch("/sessions/{session_id}")
async def update_session(session_id: int, title: str = Body(None), archive: bool = Body(None), is_archived: bool = Body(None)):
    logger.info(f"Updating session {session_id}: title={title}, archive={archive}, is_archived={is_archived}")
    conn = get_db_connection()
    c = conn.cursor()
    if title is not None:
        c.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
    if archive is not None:
        c.execute("UPDATE sessions SET is_archived = ? WHERE id = ?", (archive, session_id))
    if is_archived is not None:
        c.execute("UPDATE sessions SET is_archived = ? WHERE id = ?", (is_archived, session_id))
    conn.commit()
    conn.close()
    return {"status": "success"}

@router.get("/sessions/archived")
async def get_archived_sessions():
    logger.info("Fetching archived sessions")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, title, created_at FROM sessions WHERE is_archived = 1 ORDER BY created_at DESC")
    sessions = c.fetchall()
    conn.close()
    return [{"id": s[0], "title": s[1], "created_at": s[2]} for s in sessions]

@router.get("/profile/stats")
async def get_profile_stats():
    logger.info("Fetching profile stats")
    conn = get_db_connection()
    c = conn.cursor()
    
    # Count total chats
    c.execute("SELECT COUNT(*) FROM sessions WHERE is_archived = 0")
    total_chats = c.fetchone()[0]
    
    # Count archived chats
    c.execute("SELECT COUNT(*) FROM sessions WHERE is_archived = 1")
    archived_chats = c.fetchone()[0]
    
    # Count files uploaded
    c.execute("SELECT COUNT(*) FROM documents")
    files_uploaded = c.fetchone()[0]
    
    conn.close()
    
    # Count collections
    client = get_chroma_client()
    collections = client.list_collections()
    
    return {
        "username": "test",
        "account": "test",
        "total_chats": total_chats,
        "archived_chats": archived_chats,
        "files_uploaded": files_uploaded,
        "collections": len(collections)
    }

@router.get("/runtime/profile")
async def get_runtime_profile():
    llama_cpp_version = "unknown"
    try:
        import llama_cpp
        llama_cpp_version = getattr(llama_cpp, "__version__", "unknown")
    except Exception:
        pass

    current = _version_tuple(llama_cpp_version)
    if current <= (0, 3, 2):
        qwen3_status = "likely_unsupported"
    elif current >= (0, 3, 16):
        qwen3_status = "likely_supported"
    else:
        qwen3_status = "unknown"

    return {
        "auto_profile": settings.AUTO_PROFILE,
        "auto_profile_strict": settings.AUTO_PROFILE_STRICT,
        "detected_profile": settings.PROFILE,
        "effective": {
            "n_ctx": settings.N_CTX,
            "chat_max_tokens": settings.CHAT_MAX_TOKENS,
            "n_threads": settings.N_THREADS,
            "n_batch": settings.N_BATCH,
            "summary_chunk_size": settings.SUMMARY_CHUNK_SIZE,
            "summary_max_chunks": settings.SUMMARY_MAX_CHUNKS,
            "n_gpu_layers": settings.N_GPU_LAYERS,
            "chat_model_format": settings.CHAT_MODEL_FORMAT,
            "profile_suggested_quant": settings.PROFILE_SUGGESTED_QUANT
        },
        "runtime": {
            "python": sys.version.split()[0],
            "llama_cpp_python": llama_cpp_version
        },
        "compatibility": {
            "qwen3_status": qwen3_status,
            "qwen3_supported": qwen3_status == "likely_supported",
            "qwen3_possible_from_version": "0.3.16+ (heuristic)",
            "notes": (
                "Qwen3 support depends on the bundled llama.cpp in your llama-cpp-python wheel. "
                "If unsupported, use Qwen2.5 GGUF or a newer prebuilt wheel if available for your platform."
            )
        }
    }

# --- Collection Endpoints ---

@router.get("/collections")
async def list_collections():
    client = get_chroma_client()
    collections = client.list_collections()
    return [{"name": c.name} for c in collections]

@router.post("/collections")
async def create_collection(collection: CollectionCreate):
    # Sanitize collection name: replace spaces and special chars with underscores
    import re
    sanitized_name = re.sub(r'[^a-zA-Z0-9_-]', '_', collection.name)
    sanitized_name = re.sub(r'_+', '_', sanitized_name).strip('_')  # Remove multiple underscores
    
    logger.info(f"Creating collection: {sanitized_name} (original: {collection.name})")
    client = get_chroma_client()
    try:
        client.create_collection(name=sanitized_name)
        return {"status": "success", "name": sanitized_name}
    except Exception as e:
        logger.error(f"Error creating collection: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/collections/{name}")
async def delete_collection(name: str):
    logger.info(f"Deleting collection: {name}")
    client = get_chroma_client()
    try:
        client.delete_collection(name=name)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting collection: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# --- Notification Endpoints ---

@router.get("/notifications")
async def get_notifications():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, message, type, task_id, progress, status, is_read, created_at FROM notifications ORDER BY created_at DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    
    tasks = []
    for r in rows:
        tasks.append({
            "id": r[0],
            "message": r[1],
            "type": r[2],
            "task_id": r[3],
            "progress": r[4],
            "status": r[5],
            "is_read": bool(r[6]),
            "timestamp": r[7]
        })
    return {"notifications": tasks}

@router.post("/notifications/{id}/read")
async def mark_notification_read(id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@router.post("/notifications/clear")
async def clear_notifications():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM notifications WHERE is_read = 1 AND status != 'processing'")
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- Document Upload with Streaming Progress ---

from typing import List

@router.get("/collections/{name}/summary")
async def get_collection_summary(name: str):
    logger.info(f"Fetching document summaries for collection: {name}")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT filename, summary FROM documents WHERE collection_name = ?", (name,))
    rows = c.fetchall()
    conn.close()
    
    summaries = [{"filename": r[0], "summary": r[1] or "No summary available."} for r in rows]
    return {"name": name, "documents": summaries}

@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    collection_name: str = Form(...),
    summarize: str = Form("false"),
    files: List[UploadFile] = File(...)
):
    # Parse summarize as boolean (form data sends strings)
    should_summarize = summarize.lower() == "true"

    logger.info(f"Starting multi-file upload for {len(files)} files to {collection_name} (summarize: {should_summarize})")
    
    upload_dir = APP_DIR / "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    
    saved_files = []
    timestamp = int(time.time())

    # 1. Save all files first
    for file in files:
        original_name = os.path.splitext(file.filename)[0]
        ext = os.path.splitext(file.filename)[1]
        safe_name = "".join([c for c in original_name if c.isalnum() or c in (' ', '-', '_')]).strip()
        new_filename = f"{safe_name}_{collection_name}_{timestamp}{ext}"
        file_path = os.path.join(upload_dir, new_filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        old_file_name = f"{original_name}_{timestamp}.{ext}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append((file.filename, new_filename, file_path))

    async def process_files():
        results = []
        for index, (orig_name, new_name, path) in enumerate(saved_files):
            try:
                progress_prefix = f"[{index+1}/{len(saved_files)}]"
                yield json.dumps({"status": "loading", "message": f"{progress_prefix} Upload Started..."}) + "\n"
                await asyncio.sleep(0) # Flush
                
                text = load_document(path)
                if not text:
                    logger.error(f"Failed to extract text: {new_name}")
                    results.append({"file": orig_name, "status": "failed", "error": "No text extracted"})
                    yield json.dumps({"status": "error", "message": f"{progress_prefix} Failed to extract text"}) + "\n"
                    await asyncio.sleep(0)
                    continue # Skip to next file

                yield json.dumps({"status": "loading", "message": f"{progress_prefix} Found {len(text)} characters in document"}) + "\n"
                await asyncio.sleep(0)
                
                chunks = split_text(text)
                yield json.dumps({"status": "chunking", "message": f"{progress_prefix} Chunked into {len(chunks)} documents"}) + "\n"
                await asyncio.sleep(0)
                
                client = get_chroma_client()
                collection = client.get_or_create_collection(name=collection_name)
                
                ids = [f"{new_name}_{i}" for i in range(len(chunks))]
                temp_metadatas = []
                for i in range(len(chunks)):
                     temp_metadatas.append({
                        "source": new_name,
                        "original_name": orig_name,
                        "chunk_index": i, 
                        "total_chunks": len(chunks),
                        "upload_timestamp": timestamp
                    })
                
                # Batch Embedding with granular progress
                BATCH_SIZE = 10
                total_chunks = len(chunks)
                all_embeddings = []
                
                for i in range(0, total_chunks, BATCH_SIZE):
                    batch_chunks = chunks[i : i + BATCH_SIZE]
                    batch_embeddings = [get_embedding(chunk) for chunk in batch_chunks]
                    all_embeddings.extend(batch_embeddings)
                    
                    current_count = min(i + BATCH_SIZE, total_chunks)
                    yield json.dumps({
                        "status": "embedding", 
                        "progress": f"{current_count}/{total_chunks}",
                        "message": f"{progress_prefix} Embedding {current_count}/{total_chunks} documents"
                    }) + "\n"
                    await asyncio.sleep(0) # Flush after each batch

                yield json.dumps({"status": "saving", "message": f"{progress_prefix} Saving to ChromaDB..."}) + "\n"
                await asyncio.sleep(0)
                
                # Add to Chroma
                collection.add(
                    documents=chunks,
                    embeddings=all_embeddings,
                    metadatas=temp_metadatas,
                    ids=ids
                )
                
                # Insert document record
                conn = get_db_connection()
                cursor = conn.cursor()
                summary_text = "Summary generation in progress..." if should_summarize else "No summary requested."
                cursor.execute("INSERT INTO documents (collection_name, filename, summary) VALUES (?, ?, ?)",
                          (collection_name, orig_name, summary_text))
                conn.commit()
                conn.close()
                
                # Only trigger summarization if requested
                if should_summarize:
                    import threading
                    import uuid
                    
                    task_id = str(uuid.uuid4())
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("INSERT INTO notifications (message, type, task_id, progress, status) VALUES (?, ?, ?, ?, ?)",
                              (f"Summarization started for {orig_name}", "info", task_id, 0, "processing"))
                    conn.commit()
                    conn.close()

                    def run_summary_thread(c_name, f_name, txt, t_id):
                        from backend.rag_engine import summarize_text, update_task_progress
                        try:
                            logger.info(f"Starting background summary thread for {f_name} (Task {t_id})")
                            summary = summarize_text(txt, task_id=t_id)
                            
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute("UPDATE documents SET summary = ? WHERE collection_name = ? AND filename = ?", 
                                      (summary, c_name, f_name))
                            c.execute("UPDATE notifications SET progress = 100, status = 'completed', message = ? WHERE task_id = ?",
                                      (f"Summary ready: {f_name}", t_id))
                            conn.commit()
                            conn.close()
                            
                            logger.info(f"Completed background summary for {f_name}")
                        except Exception as e:
                            logger.error(f"Background summary thread failed: {e}")
                            try:
                                conn = get_db_connection()
                                c = conn.cursor()
                                c.execute("UPDATE notifications SET status = 'failed', message = ? WHERE task_id = ?",
                                          (f"Summary failed for {f_name}", t_id))
                                conn.commit()
                                conn.close()
                            except: pass

                    thread = threading.Thread(target=run_summary_thread, args=(collection_name, orig_name, text, task_id))
                    thread.daemon = True
                    thread.start()
                    
                    yield json.dumps({"status": "summary_started", "message": f"Summarization started for {orig_name}", "task_id": task_id}) + "\n"
                    await asyncio.sleep(0)
                
                results.append({"file": orig_name, "status": "success", "chunks": len(chunks)})
                yield json.dumps({"status": "completed", "message": f"{progress_prefix} Done!"}) + "\n"
                await asyncio.sleep(0)

                
            except Exception as e:
                logger.error(f"Upload failed for {orig_name}: {e}")
                results.append({"file": orig_name, "status": "failed", "error": str(e)})
                yield json.dumps({"status": "error", "message": f"{progress_prefix} Error: {str(e)}"}) + "\n"
        
        # specific 'summary' event or just final message
        yield json.dumps({"status": "all_completed", "results": results, "message": "All files processed."}) + "\n"

    return StreamingResponse(process_files(), media_type="application/x-ndjson")
