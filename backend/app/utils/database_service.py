"""
Database operations for chat sessions, messages, and user data.
"""

from typing import List, Dict
from datetime import datetime
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from langchain_core.messages import AIMessage, HumanMessage

from app.core.connections import pool
from app.utils.cache_service import add_message_to_cache


def ensure_session_exists(session_id: str, user_id: str = None):
    """Ensure chat session exists in database"""
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Check if session exists
            cur.execute("SELECT 1 FROM chat_session WHERE session_id = %s", (session_id,))
            exists = cur.fetchone()

            # If not, create it
            if not exists:
                cur.execute("""
                    INSERT INTO chat_session (session_id, user_id, created_at, is_active)
                    VALUES (%s, %s, %s, %s)
                """, (session_id, user_id, datetime.now(), True))
                
        conn.commit()
        print(f"✅ Session {session_id} ensured")
    except Exception as e:
        print(f"❌ Error ensuring session: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to create session")
    finally:
        pool.putconn(conn)


def save_messages_to_db(session_id: str, user_message: str, ai_response: str, source: str = None):
    """Save messages with flat, efficient schema"""
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # User message
            user_msg = {
                "type": "human",
                "content": user_message,
                "source": "user"
            }
            
            # AI message with source
            ai_msg = {
                "type": "ai",
                "content": ai_response
            }
            
            # Add source to the JSON if provided
            if source:
                ai_msg["source"] = source
            
            cur.execute(
                "INSERT INTO ai_chat_history (session_id, message) VALUES (%s, %s)",
                (session_id, Jsonb(user_msg))
            )
            cur.execute(
                "INSERT INTO ai_chat_history (session_id, message) VALUES (%s, %s)",
                (session_id, Jsonb(ai_msg))
            )
            
        conn.commit()
        print(f"✅ Saved messages for session {session_id}")
        
        # Update cache with new messages
        human_langchain_msg = HumanMessage(content=user_message)
        ai_langchain_msg = AIMessage(content=ai_response)
        
        add_message_to_cache(session_id, human_langchain_msg, K=10)
        add_message_to_cache(session_id, ai_langchain_msg, K=10)
        
    except Exception as e:
        print(f"❌ Error saving messages: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to save messages")
    finally:
        pool.putconn(conn)


def get_user_messages(session_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
    """Get messages for UI display (not LLM context)"""
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT message, created_at
                FROM ai_chat_history
                WHERE session_id = %s
                ORDER BY id DESC
                OFFSET %s LIMIT %s
            """, (session_id, offset, limit))
            
            rows = cur.fetchall()
            rows.reverse()  # chronological order for UI
            
            return [
                {
                    "id": offset + i,
                    "type": row[0]["type"],
                    "content": row[0]["content"],
                    "timestamp": row[1].isoformat() if row[1] else None,
                    "source": row[0].get("source")
                }
                for i, row in enumerate(rows)
            ]
    except Exception as e:
        print(f"❌ Error getting messages: {e}")
        return []
    finally:
        pool.putconn(conn)


def get_raw_message_history(session_id: str, limit: int = 10) -> List:
    """Get messages with cache-first approach"""
    from app.utils.cache_service import get_cached_recent_messages, cache_recent_messages
    
    print(f"Fetching history for session_id={session_id}")
    # Try cache first
    cached_messages = get_cached_recent_messages(session_id, K=limit)
    if cached_messages:
        print(f"✅ Retrieved {len(cached_messages)} messages from cache")
        return cached_messages
    
    # Fallback to DB
    print("📀 Cache miss, fetching from database")
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT message, created_at, id
                FROM ai_chat_history
                WHERE session_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (session_id, limit),
            )
            rows = cur.fetchall()

        messages = []
        for row in reversed(rows):
            msg_dict = row[0]
            msg_type = msg_dict.get("type")
            content = msg_dict.get("content", "")

            if msg_type == "human":
                messages.append(HumanMessage(content=content))
            elif msg_type == "ai":
                messages.append(AIMessage(content=content))

        # Cache the fetched messages for next time
        if messages:
            cache_recent_messages(session_id, messages, K=limit)

        return messages
    except Exception as e:
        print(f"Error fetching message history: {e}")
        return []
    finally:
        pool.putconn(conn)
