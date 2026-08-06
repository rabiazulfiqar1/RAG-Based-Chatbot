"""
Redis cache operations for chat messages, summaries, and semantic caching.
"""

import json
from typing import Dict, List, Optional
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage

from app.core.connections import redis_client, pool
from app.core.constants import REDIS_TTL


def safe_redis_operation(func, *args, **kwargs):
    """Safely execute Redis operations with fallback"""
    if not redis_client:
        return None
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"Redis operation failed: {e}")
        return None


async def cache_summary_state(session_id: str, summary_state: Dict) -> None:
    if redis_client:
        redis_key = f"chat:summary_state:{session_id}"
        serializable_state = summary_state.copy()
        if serializable_state['last_updated']:
            serializable_state['last_updated'] = serializable_state['last_updated'].isoformat()
        safe_redis_operation(redis_client.setex, redis_key, REDIS_TTL, json.dumps(serializable_state))

    async with pool.connection() as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE chat_session
                    SET summary = %s, summary_count = %s, updated_at = %s
                    WHERE session_id = %s
                """, (
                    summary_state['previous_summary'],
                    summary_state['summarized_count'],
                    summary_state['last_updated'],
                    session_id
                ))
            await conn.commit()
        except Exception as e:
            print(f"Error updating summary state in DB: {e}")
            await conn.rollback()


async def get_summary_state(session_id: str) -> Dict:
    if redis_client:
        redis_key = f"chat:summary_state:{session_id}"
        cached_state = safe_redis_operation(redis_client.get, redis_key)
        if cached_state:
            try:
                state = json.loads(cached_state)
                if state.get('last_updated'):
                    state['last_updated'] = datetime.fromisoformat(state['last_updated'])
                return state
            except (json.JSONDecodeError, ValueError):
                pass

    async with pool.connection() as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT summary, summary_count, updated_at FROM chat_session WHERE session_id = %s",
                    (session_id,)
                )
                row = await cur.fetchone()
                if row and row[0]:
                    state = {
                        'previous_summary': row[0],
                        'summarized_count': row[1] or 0,
                        'last_updated': row[2]
                    }
                    await cache_summary_state(session_id, state)
                    return state
        except Exception as e:
            print(f"Error fetching summary state from DB: {e}")

    return {'previous_summary': None, 'summarized_count': 0, 'last_updated': None}

def cache_recent_messages(session_id: str, messages: List[Dict], K: int = 10) -> None:
    """Cache last K messages using Redis list operations"""
    if not redis_client:
        return
    
    redis_key = f"chat:recent_msgs:{session_id}"
    
    try:
        serializable_msgs = []
        for msg in messages[-K:]:
            msg_data = {
                "type": msg.type,
                "content": msg.content,
                "timestamp": datetime.now().isoformat()
            }
            serializable_msgs.append(json.dumps(msg_data))
        
        pipe = redis_client.pipeline()
        pipe.delete(redis_key)
        if serializable_msgs:
            pipe.lpush(redis_key, *serializable_msgs)
            pipe.expire(redis_key, REDIS_TTL)
        pipe.execute()
        
    except Exception as e:
        print(f"Error caching recent messages: {e}")


def get_cached_recent_messages(session_id: str, K: int = 10) -> List:
    """Get cached recent messages from Redis"""
    if not redis_client:
        return []
    
    redis_key = f"chat:recent_msgs:{session_id}"
    
    try:
        cached_msgs = safe_redis_operation(redis_client.lrange, redis_key, 0, K-1)
        if not cached_msgs:
            return []
        
        messages = []
        for msg_str in reversed(cached_msgs):
            try:
                msg_data = json.loads(msg_str)
                msg_type = msg_data.get("type")
                content = msg_data.get("content", "")
                
                if msg_type == "human":
                    messages.append(HumanMessage(content=content))
                elif msg_type == "ai":
                    messages.append(AIMessage(content=content))
                    
            except (json.JSONDecodeError, KeyError):
                continue
                
        return messages
        
    except Exception as e:
        print(f"Error getting cached messages: {e}")
        return []


def add_message_to_cache(session_id: str, message, K: int = 5) -> None:
    """Add a single message to cache and maintain K limit"""
    if not redis_client:
        return
    
    redis_key = f"chat:recent_msgs:{session_id}"
    
    try:
        msg_data = {
            "type": message.type,
            "content": message.content,
            "timestamp": datetime.now().isoformat()
        }
        
        # Use pipeline for atomic operations
        pipe = redis_client.pipeline()
        pipe.lpush(redis_key, json.dumps(msg_data))
        pipe.ltrim(redis_key, 0, K-1)  # Keep only last K
        pipe.expire(redis_key, REDIS_TTL)  # Refresh TTL
        pipe.execute()
        
    except Exception as e:
        print(f"Error adding message to cache: {e}")
