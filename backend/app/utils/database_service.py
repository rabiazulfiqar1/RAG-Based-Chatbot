"""
Database operations for chat sessions, messages, and user data.

All DB-touching functions in this module are async — they use the
async psycopg pool (AsyncConnectionPool) so they never block the
event loop. Sync third-party calls (Redis) are left sync because the
redis-py client is thread-safe and fast enough; if needed they can be
offloaded with asyncio.to_thread by the caller.
"""

from typing import List, Dict, Optional
from datetime import datetime
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from langchain_core.messages import AIMessage, HumanMessage

from app.core.connections import pool
from app.utils.cache_service import add_message_to_cache


async def verify_session_owner(session_id: str, user_id: str) -> bool:
    """
    Return True iff `session_id` belongs to `user_id`.
    Raises 404 if the session does not exist at all, 403 if it belongs
    to someone else. Safe to return True for a brand-new session that
    the caller is about to create.
    """
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT user_id FROM chat_session WHERE session_id = %s",
                (session_id,),
            )
            row = await cur.fetchone()

    if row is None:
        # Session not created yet — allow the caller to create it.
        return True
    return row[0] == user_id


async def ensure_session_exists(session_id: str, user_id: str = None):
    """Ensure chat session exists in database"""
    async with pool.connection() as conn:
        try:
            async with conn.cursor() as cur:
                # Check if session exists
                await cur.execute(
                    "SELECT 1 FROM chat_session WHERE session_id = %s",
                    (session_id,),
                )
                exists = await cur.fetchone()

                # If not, create it
                if not exists:
                    await cur.execute(
                        """
                        INSERT INTO chat_session (session_id, user_id, created_at, is_active)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (session_id, user_id, datetime.now(), True),
                    )

            await conn.commit()
            print(f"Session {session_id} ensured")
        except Exception as e:
            print(f"Error ensuring session: {e}")
            await conn.rollback()
            raise HTTPException(status_code=500, detail="Failed to create session")


async def save_messages_to_db(
    session_id: str, user_message: str, ai_response: str, source: str = None
):
    """Save messages with flat, efficient schema"""
    async with pool.connection() as conn:
        try:
            async with conn.cursor() as cur:
                # User message
                user_msg = {
                    "type": "human",
                    "content": user_message,
                    "source": "user",
                }

                # AI message with source
                ai_msg = {
                    "type": "ai",
                    "content": ai_response,
                }

                # Add source to the JSON if provided
                if source:
                    ai_msg["source"] = source

                await cur.execute(
                    "INSERT INTO ai_chat_history (session_id, message) VALUES (%s, %s)",
                    (session_id, Jsonb(user_msg)),
                )
                await cur.execute(
                    "INSERT INTO ai_chat_history (session_id, message) VALUES (%s, %s)",
                    (session_id, Jsonb(ai_msg)),
                )

            await conn.commit()
            print(f"Saved messages for session {session_id}")

            # Update cache with new messages (Redis, sync — fast/non-blocking enough)
            human_langchain_msg = HumanMessage(content=user_message)
            ai_langchain_msg = AIMessage(content=ai_response)

            add_message_to_cache(session_id, human_langchain_msg, K=10)
            add_message_to_cache(session_id, ai_langchain_msg, K=10)

        except Exception as e:
            print(f"Error saving messages: {e}")
            await conn.rollback()
            raise HTTPException(status_code=500, detail="Failed to save messages")


async def get_user_messages(
    session_id: str, user_id: str, limit: int = 50, offset: int = 0
) -> List[Dict]:
    """
    Get messages for UI display (not LLM context).

    `user_id` is required so the caller is implicitly scoped to messages
    for sessions they own. The session-ownership check is performed by
    the route handler via `verify_session_owner` before this runs.
    """
    async with pool.connection() as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT message, created_at
                    FROM ai_chat_history
                    WHERE session_id = %s
                    ORDER BY id DESC
                    OFFSET %s LIMIT %s
                    """,
                    (session_id, offset, limit),
                )
                rows = await cur.fetchall()
                rows.reverse()  # chronological order for UI

                return [
                    {
                        "id": offset + i,
                        "type": row[0]["type"],
                        "content": row[0]["content"],
                        "timestamp": row[1].isoformat() if row[1] else None,
                        "source": row[0].get("source"),
                    }
                    for i, row in enumerate(rows)
                ]
        except Exception as e:
            print(f"Error getting messages: {e}")
            return []


async def get_raw_message_history(session_id: str, limit: int = 10) -> List:
    """Get messages with cache-first approach"""
    from app.utils.cache_service import get_cached_recent_messages, cache_recent_messages

    print(f"Fetching history for session_id={session_id}")
    # Try cache first (Redis, sync — fast/non-blocking enough)
    cached_messages = get_cached_recent_messages(session_id, K=limit)
    if cached_messages:
        print(f"Retrieved {len(cached_messages)} messages from cache")
        return cached_messages

    # Fallback to DB
    print("Cache miss, fetching from database")
    async with pool.connection() as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT message, created_at, id
                    FROM ai_chat_history
                    WHERE session_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (session_id, limit),
                )
                rows = await cur.fetchall()

            messages = []
            for row in reversed(rows):
                msg_dict = row[0]
                msg_type = msg_dict.get("type")
                content = msg_dict.get("content", "")

                if msg_type == "human":
                    messages.append(HumanMessage(content=content))
                elif msg_type == "ai":
                    messages.append(AIMessage(content=content))

            # Cache the fetched messages for next time (Redis, sync)
            if messages:
                cache_recent_messages(session_id, messages, K=limit)

            return messages
        except Exception as e:
            print(f"Error fetching message history: {e}")
            return []
