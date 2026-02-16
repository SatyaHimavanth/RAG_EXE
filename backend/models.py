from pydantic import BaseModel
from typing import List, Optional

class ChatMessage(BaseModel):
    role: str
    content: str
    
class ChatRequest(BaseModel):
    session_id: Optional[int] = None
    collection_name: Optional[str] = None
    messages: List[ChatMessage]
    stream: bool = True

class ChatResponse(BaseModel):
    content: str
    token_count: Optional[int] = 0
    time_taken: Optional[float] = 0.0


class CollectionCreate(BaseModel):
    name: str

class CollectionInfo(BaseModel):
    name: str
    count: int

class DocInfo(BaseModel):
    filename: str
    upload_date: str
    
class ChatSession(BaseModel):
    id: int
    title: str
    created_at: str
    messages: List[ChatMessage]
