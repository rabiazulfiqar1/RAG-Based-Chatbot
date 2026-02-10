"""
Document processing utilities for loading, chunking, and embedding documents.
"""

import os
import hashlib
import mimetypes
import tempfile
from typing import List
from datetime import datetime
from fastapi import HTTPException
from langchain_core.documents import Document
from langchain_community.document_loaders import (
    PyPDFLoader, TextLoader, WebBaseLoader,
    UnstructuredWordDocumentLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
import bs4

from app.core.connections import document_vector_store, pool
from app.core.constants import CHUNK_SIZE, CHUNK_OVERLAP


def get_file_hash(file_content: bytes) -> str:
    """Generate hash for file deduplication"""
    return hashlib.md5(file_content).hexdigest()


def load_document_by_type(file_path: str, filename: str) -> List[Document]:
    """Load document based on file type"""
    mime_type, _ = mimetypes.guess_type(filename)
    
    try:
        if mime_type == "application/pdf":
            loader = PyPDFLoader(file_path)
        elif mime_type == "text/plain":
            loader = TextLoader(file_path, encoding="utf-8")
        elif mime_type in ["application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                          "application/msword"]:
            loader = UnstructuredWordDocumentLoader(file_path)
        else:
            # Try as text file for unknown types
            loader = TextLoader(file_path, encoding="utf-8")
            
        return loader.load()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error loading {filename}: {str(e)}")


def load_web_document(url: str) -> List[Document]:
    """Load document from web URL"""
    try:
        loader = WebBaseLoader(
            web_paths=[str(url)],
            bs_kwargs=dict(
                parse_only=bs4.SoupStrainer(
                    class_=("content", "post-content", "article", "main", "body")
                )
            ),
        )
        docs = loader.load()
        
        if not docs or not docs[0].page_content.strip():
            # Fallback: load entire page
            loader = WebBaseLoader(web_paths=[str(url)])
            docs = loader.load()
            
        return docs
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error loading URL: {str(e)}")


def clean_text(text: str) -> str:
    """Remove null bytes from text"""
    if not text:
        return ""
    return text.replace("\x00", "")


def chunk_and_embed_document(
    docs: List[Document],
    session_id: str,
    document_id: str,
    filename: str,
    user_id: str
) -> int:
    """Chunk document and add to vector store"""
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    chunks = text_splitter.split_documents(docs)
    
    # Add metadata to chunks
    for i, chunk in enumerate(chunks):
        chunk.page_content = clean_text(chunk.page_content)
        chunk.metadata.update({
            "session_id": session_id,
            "document_id": document_id,
            "filename": filename,
            "user_id": user_id,
            "chunk_id": f"{document_id}_chunk_{i}",
            "chunk_index": i,
            "total_chunks": len(chunks),
            "created_at": datetime.now().isoformat()
        })
    
    # Add to vector store
    document_vector_store.add_documents(chunks)
    return len(chunks)


def save_document_metadata(
    document_id: str,
    session_id: str,
    user_id: str,
    filename: str,
    file_type: str,
    file_size: int,
    chunk_count: int,
    file_hash: str = None,
    url: str = None
):
    """Save document metadata to database"""
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_documents
                (document_id, session_id, user_id, filename, file_type, file_size,
                 chunk_count, file_hash, url, created_at, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (document_id) DO UPDATE SET
                    updated_at = CURRENT_TIMESTAMP
            """, (
                document_id, session_id, user_id, filename, file_type,
                file_size, chunk_count, file_hash, url, datetime.now(), True
            ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        pool.putconn(conn)

def get_session_document_count(session_id: str, user_id: str) -> int:
    """Get count of active documents for a session"""
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) 
                FROM user_documents 
                WHERE session_id = %s AND user_id = %s AND is_active = true
            """, (session_id, user_id))
            count = cur.fetchone()[0]
            return count
    except Exception as e:
        print(f"Error getting document count: {e}")
        return 0
    finally:
        pool.putconn(conn)