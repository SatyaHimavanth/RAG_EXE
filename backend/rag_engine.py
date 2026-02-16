from llama_cpp import Llama
import chromadb
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

# Suppress llama.cpp verbose output
sys.stderr = open(os.devnull, "w")

# Model Configurations
CHAT_MODEL_PATH = str(settings.CHAT_MODEL_PATH)
EMBED_MODEL_PATH = str(settings.EMBED_MODEL_PATH)

logger.info(f"Initializing Chat Model: {CHAT_MODEL_PATH}")
# Initialize Chat Model
try:
    llm = Llama(
        model_path=CHAT_MODEL_PATH,
        n_gpu_layers=settings.N_GPU_LAYERS, 
        n_ctx=settings.N_CTX,
        chat_format=settings.CHAT_MODEL_FORMAT,
        verbose=False
    )
except Exception as e:
    logger.error("Error loading the Chat Model")
    sys.exit(0)

logger.info(f"Initializing Embed Model: {EMBED_MODEL_PATH}")
# Initialize Embed Model
try:
    embed_model = Llama(
        model_path=EMBED_MODEL_PATH,
        embedding=True,
        verbose=False
    )
except Exception as e:
    logger.error("Error loading the Embed Model")
    sys.exit(0)

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

    for m in messages[-2:]:
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
        stream=True
    )
    
    for chunk in stream:
        if 'content' in chunk['choices'][0]['delta']:
            content = chunk['choices'][0]['delta']['content']
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

def recursive_summarize(text: str, depth: int = 0, task_id: str = None, current_progress: int = 0, progress_step: int = 100) -> str:
    """
    Recursively summarizes text.
    task_id: UUID for database progress updates.
    current_progress: Base progress for this chunk.
    progress_step: How much this chunk contributes to total progress.
    """
    SUMMARY_CHUNK_SIZE = settings.SUMMARY_CHUNK_SIZE
    
    if len(text) <= SUMMARY_CHUNK_SIZE:
        prompt = f"""Identify and list the key points from the text below. Do not repeat information.
        
            Text:
            {text}

            Key Points:
            -"""
        try:
            output = llm.create_completion(
                prompt=prompt,
                max_tokens=500,
                stop=["\n\n", "User:", "Human:"],
                temperature=0.2,
                repeat_penalty=1.2
            )
            
            if task_id:
                new_progress = min(current_progress + progress_step, 99)
                update_task_progress(task_id, int(new_progress))

            return "- " + output['choices'][0]['text'].strip()
        except Exception as e:
            logger.error(f"Error in base summary at depth {depth}: {e}")
            return "Error summarizing chunk."

    chunks = []
    start = 0
    while start < len(text):
        end = start + SUMMARY_CHUNK_SIZE
        if end < len(text):
            lookback = text[end-1000:end]
            last_period = lookback.rfind('.')
            last_newline = lookback.rfind('\n')
            split_point = max(last_period, last_newline)
            
            if split_point != -1:
                end = (end - 1000) + split_point + 1
        
        chunks.append(text[start:end])
        start = end

    logger.info(f"Recursive summary depth {depth}: Splitting {len(text)} chars into {len(chunks)} chunks")
    
    chunk_summaries = []
    chunk_step = progress_step / len(chunks) if chunks else 0
    
    for i, chunk in enumerate(chunks):
        logger.info(f"Summarizing chunk {i+1}/{len(chunks)} at depth {depth}")
        
        sub_progress_base = current_progress + (i * chunk_step)
        
        summary = recursive_summarize(chunk, depth=depth+1, task_id=task_id, current_progress=sub_progress_base, progress_step=chunk_step)
        
        if summary != "Error summarizing chunk.":
            chunk_summaries.append(summary)
        
    if not chunk_summaries:
        return "Could not generate summary."

    combined_summary = "\n".join(chunk_summaries)
    
    return recursive_summarize(combined_summary, depth=depth+1, task_id=task_id, current_progress=current_progress + progress_step - 5, progress_step=5)

def summarize_text(text: str, task_id: str = None) -> str:
    """Public wrapper for recursive summarization."""
    try:
        logger.info(f"Starting summarization for text length: {len(text)}")
        return recursive_summarize(text, task_id=task_id)
    except Exception as e:
        logger.error(f"Top level summary error: {e}")
        return "Summary generation failed."