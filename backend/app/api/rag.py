import os
import json
import asyncio
import tempfile
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, BackgroundTasks, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
import re

# Import models
from app.models.schemas import MessageRequest, DocumentUploadRequest, DocumentQuestionRequest

# Import core dependencies
from app.core.connections import llm, pool, redis_client
from app.core.constants import SUMMARY_BATCH_SIZE, MAX_DOCUMENTS_PER_SESSION

# Import utilities
from app.utils.cache_service import (
    get_cached_recent_messages
)
from app.utils.document_service import (
    get_file_hash,
    load_document_by_type,
    load_web_document,
    chunk_and_embed_document,
    save_document_metadata,
    get_session_document_count
)
from app.utils.database_service import (
    ensure_session_exists,
    save_messages_to_db,
    get_user_messages,
    verify_session_owner
)

# Import services
from app.services.rag_service import rag_graph
from app.services.chat_service import (
    chat_prompt,
    get_conversation_context,
    perform_background_summarization
)

from app.utils.rate_limiter import RateLimiter

chat_rate_limiter = RateLimiter(
    max_requests=10, window_seconds=86400, prefix="rl:chat",
    global_max_requests=60, global_window_seconds=86400,
)

upload_rate_limiter = RateLimiter(
    max_requests=2, window_seconds=86400, prefix="rl:upload",
    global_max_requests=15, global_window_seconds=86400,
)

# Import authentication
from app.auth.supabase_auth import get_current_user

router = APIRouter()


@router.post("/documents/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    current_user: Dict[str, Any] = Depends(upload_rate_limiter)
):
    """Upload and process document (file or URL)"""

    if not file and not url:
        raise HTTPException(status_code=400, detail="Either file or URL must be provided")

    user_id = current_user.get("id")

    # Check document limit
    current_count = await get_session_document_count(session_id, user_id)
    if current_count >= MAX_DOCUMENTS_PER_SESSION:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_DOCUMENTS_PER_SESSION} documents allowed per session. Please remove some documents first."
        )

    try:
        if file:
            # Handle file upload
            file_content = await file.read()
            file_hash = get_file_hash(file_content)

            # Check for duplicates
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT document_id, filename, file_type, file_size, chunk_count, url FROM user_documents WHERE file_hash = %s AND user_id = %s AND is_active = true",
                        (file_hash, user_id)
                    )
                    existing = await cur.fetchone()
                    if existing:
                        return {"document": {
                            "message": "Document already exists",
                            "document_id": existing[0],
                            "filename": existing[1],
                            "file_type": existing[2],
                            "file_size": existing[3],
                            "chunk_count": existing[4],
                            "url": existing[5],
                            "is_web_page": bool(existing[5])
                        }}

            # Save to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp_file:
                tmp_file.write(file_content)
                tmp_path = tmp_file.name

            document_id = f"doc_{session_id}_{int(datetime.now().timestamp())}"
            filename = file.filename
            file_type = file.content_type or "application/octet-stream"
            file_size = len(file_content)

            try:
                # Process document (blocking work off the event loop)
                docs = await asyncio.to_thread(load_document_by_type, tmp_path, filename)
                chunk_count = await asyncio.to_thread(
                    chunk_and_embed_document, docs, session_id, document_id, filename, user_id
                )

                # Save metadata
                await save_document_metadata(
                    document_id, session_id, user_id, filename,
                    file_type, file_size, chunk_count, file_hash
                )

            finally:
                # Cleanup temp file
                os.unlink(tmp_path)

        else:
            # Handle URL - check for duplicates first
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """SELECT document_id, filename, file_type, file_size, chunk_count, url
                        FROM user_documents
                        WHERE url = %s AND session_id = %s AND user_id = %s AND is_active = true""",
                        (url, session_id, user_id)
                    )
                    existing = await cur.fetchone()
                    if existing:
                        print(f"Duplicate URL detected: {url}")
                        return {"document": {
                            "message": "This URL is already added to this session",
                            "document_id": existing[0],
                            "filename": existing[1],
                            "file_type": existing[2],
                            "file_size": existing[3],
                            "chunk_count": existing[4],
                            "url": existing[5],
                            "is_web_page": bool(existing[5]),
                            "is_duplicate": True
                        }}

            # Process new URL
            document_id = f"url_{session_id}_{int(datetime.now().timestamp())}"

            docs = await asyncio.to_thread(load_web_document, url)
            filename = f"Web Page: {url}"
            chunk_count = await asyncio.to_thread(
                chunk_and_embed_document, docs, session_id, document_id, filename, user_id
            )

            # Estimate content size
            file_size = sum(len(doc.page_content) for doc in docs)

            await save_document_metadata(
                document_id, session_id, user_id, filename,
                "text/html", file_size, chunk_count, url=url
            )

        return {"document": {
            "message": "Document processed successfully",
            "document_id": document_id,
            "filename": filename,
            "file_type": file.content_type if file else "text/html",
            "file_size": file_size,
            "chunk_count": chunk_count,
            "url": url if url else None,
            "is_web_page": bool(url)
        }}

    except Exception as e:
        print(f"Document upload error: {e}")
        raise HTTPException(status_code=500, detail="Document processing failed")


@router.get("/documents/list")
async def list_documents(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """List all active documents for a session"""
    user_id = current_user.get("id")

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT document_id, filename, file_type, file_size, chunk_count, url, created_at
                    FROM user_documents
                    WHERE session_id = %s AND user_id = %s AND is_active = true
                    ORDER BY created_at DESC
                """, (session_id, user_id))

                rows = await cur.fetchall()
                documents = []

                for row in rows:
                    doc_id, filename, file_type, file_size, chunk_count, url, created_at = row
                    documents.append({
                        "document_id": doc_id,
                        "filename": filename,
                        "file_type": file_type,
                        "file_size": file_size,
                        "chunk_count": chunk_count,
                        "url": url,
                        "is_web_page": bool(url),
                        "created_at": created_at.isoformat()
                    })

                return {
                    "documents": documents,
                    "count": len(documents),
                    "max_allowed": MAX_DOCUMENTS_PER_SESSION
                }

    except Exception as e:
        print(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to list documents")


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Delete a document and its embeddings"""

    user_id = current_user.get("id")

    async with pool.connection() as conn:
        try:
            async with conn.cursor() as cur:
                # 1. Delete the document row
                await cur.execute(
                    """
                    DELETE FROM user_documents
                    WHERE document_id = %s AND user_id = %s
                    RETURNING filename
                    """,
                    (document_id, user_id)
                )
                deleted = await cur.fetchone()

                if not deleted:
                    raise HTTPException(status_code=404, detail="Document not found")

                # 2. Delete embeddings linked to that document
                await cur.execute(
                    """
                    DELETE FROM langchain_pg_embedding
                    WHERE cmetadata->>'document_id' = %s
                    """,
                    (document_id,)
                )

            await conn.commit()

            return {
                "message": "Document deleted successfully",
                "filename": deleted[0]
            }

        except HTTPException:
            raise
        except Exception as e:
            await conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/mentor/enhanced-chat")
async def enhanced_chat(
    request: MessageRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(chat_rate_limiter)
):
    """
    Enhanced chat that can handle both regular conversation and document questions
    Returns Server-Sent Events (SSE) stream
    caching:
    - Generates new response if cache miss
    - Saves to cache for future use
    """
    try:
        user_id = current_user.get("id")
        session_id = request.session_id
        message = request.message
        selected_document_ids = request.selected_document_ids or []

        # STEP 1: Check semantic cache (works across all users!)
        # if not selected_document_ids:
        #     cached_response = await get_semantic_cached_response(message)

        #     if cached_response:
        #         # Stream cached response
        #         async def cached_stream():
        #             tokens = re.findall(r'\S+|\s+', cached_response)
        #             for token in tokens:
        #                 yield f"data: {json.dumps({'token': token})}\n\n"
        #                 await asyncio.sleep(0.02)

        #             yield f"data: {json.dumps({'done': True})}\n\n"

        #         # Save to this session's DB history
        #         await save_messages_to_db(session_id, message, cached_response, source="semantic_cache")

        #         return StreamingResponse(
        #             cached_stream(),
        #             media_type="text/event-stream",
        #             headers={
        #                 "Cache-Control": "no-cache",
        #                 "X-Accel-Buffering": "no"
        #             }
        #         )

        # If documents are selected, try document Q&A
        document_answer = None
        source_documents = []

        if selected_document_ids:
            try:
                rag_response = await rag_graph.ainvoke({
                    "question": message,
                    "session_id": session_id,
                    "document_ids": selected_document_ids
                })

                # Check if we found relevant context
                if rag_response.get("context") and len(rag_response["context"]) > 0:
                    document_answer = rag_response["answer"]
                    source_documents = list(set([
                        doc.metadata.get("filename", "Unknown")
                        for doc in rag_response["context"]
                    ]))

            except Exception as e:
                print(f"Document Q&A failed: {e}")

        # If document Q&A found an answer, use it. Otherwise, use regular chat
        if document_answer and "cannot find" not in document_answer.lower():
            source = "documents"

            # Stream document answer
            async def doc_stream():
                # Send document source indicator first
                header = "**Based on your uploaded documents:**\n\n"
                yield f"data: {json.dumps({'token': header})}\n\n"
                await asyncio.sleep(0.05)

                tokens = re.findall(r'\S+|\s+', document_answer)

                for token in tokens:
                    yield f"data: {json.dumps({'token': token})}\n\n"
                    await asyncio.sleep(0.02)

                yield f"data: {json.dumps({'done': True})}\n\n"

            # Save full response to DB
            full_response = f"📄 **Based on: {', '.join(source_documents)}**\n\n{document_answer}"
            await save_messages_to_db(session_id, message, full_response, source=source)

            return StreamingResponse(
                doc_stream(),
                media_type="text/event-stream"
            )

        else:

            await ensure_session_exists(request.session_id, user_id)
            final_history = await get_conversation_context(request.session_id, K=5, SUMMARY_BATCH_SIZE=5)

            # Stream LLM response
            full_response = []

            async def chat_stream():
                nonlocal full_response
                async for chunk in llm.astream(
                    chat_prompt.format_messages(
                        message=message,
                        chat_history=final_history
                    )
                ):
                    if chunk.content:
                        full_response.append(chunk.content)
                        yield f"data: {json.dumps({'token': chunk.content})}\n\n"

                yield f"data: {json.dumps({'done': True})}\n\n"

            # Save response after streaming completes
            async def save_after_stream():
                # Wait a bit for stream to complete
                await asyncio.sleep(0.5)
                complete_response = "".join(full_response)

                await save_messages_to_db(session_id, message, complete_response, source="general")

                # Save to semantic cache (session-independent!)
                # await save_to_semantic_cache(message, complete_response)

                # Background summarization
                cached_messages = get_cached_recent_messages(session_id, K=10)
                if len(cached_messages) > 5:
                    background_tasks.add_task(
                        perform_background_summarization,
                        session_id,
                        cached_messages,
                        K=5,
                        SUMMARY_BATCH_SIZE=5
                    )

            background_tasks.add_task(save_after_stream)

            return StreamingResponse(
                chat_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no"
                }
            )

    except Exception as e:
        print(f"Enhanced chat error: {e}")
        raise HTTPException(status_code=500, detail="Chat service temporarily unavailable")


@router.get("/messages/{session_id}")
async def get_messages(
    session_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user.get("id")
    # verify the session belongs to this user before returning anything
    if not await verify_session_owner(session_id, user_id):
        raise HTTPException(status_code=403, detail="Not authorized for this session")
    messages = await get_user_messages(session_id, limit, offset)
    return messages or []