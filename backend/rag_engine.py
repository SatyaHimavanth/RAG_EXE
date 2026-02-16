from llama_cpp import Llama
import sys
import os
import time
import asyncio
from typing import List, Generator
from backend.models import ChatMessage
from backend.database import get_chroma_client
from backend.config import settings, APP_DIR, BUNDLE_DIR
from backend.logger import setup_logger

logger = setup_logger(__name__)

# Do not globally suppress stderr in packaged apps; it hides fatal startup errors.

# Model Configurations
CHAT_MODEL_PATH = str(settings.CHAT_MODEL_PATH)
EMBED_MODEL_PATH = str(settings.EMBED_MODEL_PATH)

logger.info(f"Initializing Chat Model: {CHAT_MODEL_PATH}")
if settings.AUTO_PROFILE:
    p = settings.PROFILE
    logger.info(
        "Auto profile active | tier=%s | total_ram_gb=%s | avail_ram_gb=%s | cores=%s | n_ctx=%s | chat_max_tokens=%s | n_threads=%s | n_batch=%s | suggested_quant=%s",
        p.get("tier"),
        p.get("total_ram_gb"),
        p.get("avail_ram_gb"),
        p.get("logical_cores"),
        settings.N_CTX,
        settings.CHAT_MAX_TOKENS,
        settings.N_THREADS,
        settings.N_BATCH,
        settings.PROFILE_SUGGESTED_QUANT,
    )
# Initialize Chat Model
try:
    llm = Llama(
        model_path=CHAT_MODEL_PATH,
        n_gpu_layers=settings.N_GPU_LAYERS, 
        n_ctx=settings.N_CTX,
        n_batch=settings.N_BATCH,
        n_threads=settings.N_THREADS,
        chat_format=settings.CHAT_MODEL_FORMAT,
        verbose=False
    )
except Exception as e:
    logger.exception(f"Error loading the Chat Model: {e}")
    raise RuntimeError(f"Failed to load chat model: {CHAT_MODEL_PATH}") from e

logger.info(f"Initializing Embed Model: {EMBED_MODEL_PATH}")
# Initialize Embed Model
try:
    embed_model = Llama(
        model_path=EMBED_MODEL_PATH,
        embedding=True,
        n_batch=settings.N_BATCH,
        n_threads=settings.N_THREADS,
        verbose=False
    )
except Exception as e:
    logger.exception(f"Error loading the Embed Model: {e}")
    raise RuntimeError(f"Failed to load embedding model: {EMBED_MODEL_PATH}") from e

def get_embedding(text: str) -> List[float]:
    # logger.debug(f"Generating embedding for text length: {len(text)}") # Verbose
    return embed_model.create_embedding(text)["data"][0]["embedding"]

def classify_intent(message: str) -> str:
    """
    Classifies if the user message is about conversation history/greetings or requires external knowledge.
    Returns: 'history' or 'knowledge'
    """
    prompt = f"""Classify the following user message into one of two categories:
        1. "history": If the user is asking about previous topics in this conversation, greeting, saying specific things like "previous question", "what did we talk about", or generic chitchat.
        2. "knowledge": If the user is asking a specific question that requires external information, documents, or knowledge base lookup.

        User Message: "{message}"

        Reply ONLY with "history" or "knowledge".
        Classification:
    """

    logger.info("Classifying user intent...")
    output = llm.create_completion(
        prompt=prompt,
        max_tokens=10,
        stop=["\n"],
        temperature=0.1
    )
    intent = output['choices'][0]['text'].strip().lower()
    logger.info(f"Intent classified as: {intent}")
    return intent if intent in ["history", "knowledge"] else "knowledge"

def chat_stream(messages: List[ChatMessage], collection_name: str = None) -> Generator[str, None, None]:
    context_str = ""
    last_message = messages[-1].content
    
    # 1. Orchestrator Step
    # intent = classify_intent(last_message)
    intent = "knowledge"
    
    # 2. Retrieval Step (only if intent is knowledge and collection is selected)
    if collection_name and intent == "knowledge":
        logger.info(f"Intent is 'knowledge'. Proceeding with RAG for collection: {collection_name}")
        client = get_chroma_client()
        try:
            collection = client.get_collection(name=collection_name)
            query_embedding = get_embedding(last_message)
            
            n_results = settings.RETRIEVED_DOCS_COUNT
            logger.info(f"Querying ChromaDB. n_results={n_results}")
            
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            
            if results and results['documents']:
                retrieved_docs = results['documents'][0]
                context_str = "\n\nRefer to the following context:\n" + "\n".join(retrieved_docs) + "\n\n"
                logger.info(f"Retrieved {len(retrieved_docs)} documents")
            else:
                logger.info("No documents retrieved")
                
        except Exception as e:
            logger.error(f"Error querying collection: {e}")
    else:
        logger.info(f"Skipping retrieval. Intent: {intent}, Collection: {collection_name}")

    system_prompt = (
        "You are an intelligent AI assistant. You have access to the entire conversation history matching the order of messages provided. "
        "Always answer based on the context of the previous messages. "
        "If the user asks about previous topics or questions, refer to the history to provide the correct answer. "
        "Respond to user in a clear, concise and professional manner."
    )
    formatted_messages = [{"role": "system", "content": system_prompt}]

    # Keep recent turns for stronger continuity without blowing context.
    for m in messages[-8:]:
        msg = m.model_dump()
        if msg['role'] == 'human':
            msg['role'] = 'user'
        elif msg['role'] == 'ai':
            msg['role'] = 'assistant'
        formatted_messages.append(msg)

    if context_str:
        if formatted_messages[-1]['role'] == 'user':
            formatted_messages[-1]['content'] = f"Context:\n{context_str}\n\nQuestion:\n{formatted_messages[-1]['content']}"
        else:
            formatted_messages[-1]['content'] += f"\n\nContext:\n{context_str}"

    start_time = time.time()
    token_count = 0
    
    logger.info(f"Sending request to LLM with {len(formatted_messages)} messages")
    stream = llm.create_chat_completion(
        messages=formatted_messages,
        max_tokens=settings.CHAT_MAX_TOKENS,
        temperature=settings.CHAT_TEMPERATURE,
        presence_penalty=settings.CHAT_PRESENCE_PENALTY,
        repeat_penalty=settings.CHAT_REPEAT_PENALTY,
        stop=["</s>", "<|im_end|>", "User:", "Human:"],
        stream=True
    )
    
    for chunk in stream:
        delta = chunk['choices'][0].get('delta', {})
        if 'content' in delta:
            content = delta['content']
            token_count += 1
            yield content

    end_time = time.time()
    duration = end_time - start_time
    
    yield f"\n\n[METRICS] Time: {duration:.2f}s | Tokens: {token_count}"

def update_task_progress(task_id: str, progress: int, status: str = "processing"):
    if not task_id:
        return
    try:
        from backend.database import get_db_connection
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE notifications SET progress = ?, status = ? WHERE task_id = ?", 
                  (progress, status, task_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to update task progress: {e}")

def _split_text_for_summary(text: str, chunk_size: int, max_chunks: int) -> List[str]:
    chunks: List[str] = []
    start = 0
    text_len = len(text)
    while start < text_len and len(chunks) < max_chunks:
        end = min(start + chunk_size, text_len)
        if end < text_len:
            lookback_start = max(start, end - 1200)
            lookback = text[lookback_start:end]
            split_point = max(lookback.rfind('\n'), lookback.rfind('. '))
            if split_point > 0:
                end = lookback_start + split_point + 1
        if end <= start:
            end = min(start + chunk_size, text_len)
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


def _summarize_chunk(chunk: str) -> str:
    prompt = f"""You are writing study notes.
Read the text and produce 5 to 8 concise bullets.
Rules:
- Keep concrete facts, numbers, names and outcomes.
- Avoid fluff and repetition.
- Each bullet should be one line.

Text:
{chunk}

Bullets:
-"""
    output = llm.create_completion(
        prompt=prompt,
        max_tokens=280,
        temperature=0.15,
        repeat_penalty=1.15,
        stop=["\n\n\n", "User:", "Human:"]
    )
    text = output['choices'][0]['text'].strip()
    return text if text else "No useful points found for this section."


def _finalize_summary(combined_points: str, target_words: int) -> str:
    prompt = f"""Create a practical document summary using the bullet notes below.
Write around {target_words} words.
Structure:
1) Overview (2-4 sentences)
2) Key Points (8-14 bullets)
3) Actionable Notes / Risks (3-6 bullets, if relevant)

Bullet notes:
{combined_points}

Summary:
"""
    output = llm.create_completion(
        prompt=prompt,
        max_tokens=min(max(int(target_words * 1.6), 260), 900),
        temperature=0.2,
        repeat_penalty=1.15,
        stop=["User:", "Human:"]
    )
    return output['choices'][0]['text'].strip()

def summarize_text(text: str, task_id: str = None) -> str:
    """Public wrapper for recursive summarization."""
    try:
        logger.info(f"Starting summarization for text length: {len(text)}")
        if not text or not text.strip():
            return "No content available for summarization."

        chunk_size = settings.SUMMARY_CHUNK_SIZE
        max_chunks = settings.SUMMARY_MAX_CHUNKS
        chunks = _split_text_for_summary(text, chunk_size, max_chunks)
        if not chunks:
            return "No content available for summarization."

        logger.info(f"Summarization chunks prepared: {len(chunks)}")
        chunk_summaries: List[str] = []

        for i, chunk in enumerate(chunks, start=1):
            logger.info(f"Summarizing chunk {i}/{len(chunks)}")
            summary = _summarize_chunk(chunk)
            chunk_summaries.append(f"Section {i}:\n{summary}")
            if task_id:
                progress = min(int((i / len(chunks)) * 85), 95)
                update_task_progress(task_id, progress)

        words = max(len(text.split()), 1)
        target_words = max(140, min(int(words * 0.22), 500))

        combined_points = "\n\n".join(chunk_summaries)
        final_summary = _finalize_summary(combined_points, target_words)

        if task_id:
            update_task_progress(task_id, 99)

        return final_summary if final_summary else "Could not generate summary."
    except Exception as e:
        logger.error(f"Top level summary error: {e}")
        return "Summary generation failed."
