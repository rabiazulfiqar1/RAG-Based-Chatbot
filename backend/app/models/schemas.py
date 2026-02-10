"""
Pydantic models for request/response validation.
"""

from pydantic import BaseModel, HttpUrl, validator
from typing import List, Optional
from langchain_core.documents import Document


class MessageRequest(BaseModel):
    """Request model for chat messages"""
    message: str
    session_id: str
    selected_document_ids: Optional[List[str]] = []  
    # has_documents: Optional[bool] = False
    # document_id: Optional[str] = None
    
    @validator('message')
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError('Message cannot be empty')
        if len(v) > 5000:
            raise ValueError('Message too long')
        return v.strip()
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or len(v) < 3:
            raise ValueError('Invalid session ID')
        return v


class DocumentUploadRequest(BaseModel):
    """Request model for document uploads"""
    session_id: str
    url: Optional[HttpUrl] = None


class DocumentQuestionRequest(BaseModel):
    """Request model for document-based questions"""
    session_id: str
    question: str
    document_ids: Optional[List[str]] = None
    
    @validator('question')
    def validate_question(cls, v):
        if not v or not v.strip():
            raise ValueError('Question cannot be empty')
        return v.strip()


class RAGState(BaseModel):
    """State model for RAG workflow"""
    question: str
    context: List[Document] = []
    answer: str = ""
    session_id: str
    document_ids: Optional[List[str]] = None
