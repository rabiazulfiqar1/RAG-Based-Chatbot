"""
Redis cache operations for chat messages, summaries, and semantic caching.
"""

import json
from typing import Dict, List, Optional
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage

from app.core.connections import redis_client, llmcache, pool
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


def cache_summary_state(session_id: str, summary_state: Dict) -> None:
    """Cache summary state in both Redis and database"""
    # Cache in Redis (fast access)
    if redis_client:
        redis_key = f"chat:summary_state:{session_id}"
        serializable_state = summary_state.copy()
        if serializable_state['last_updated']:
            serializable_state['last_updated'] = serializable_state['last_updated'].isoformat()
        
        safe_redis_operation(
            redis_client.setex,
            redis_key,
            REDIS_TTL,
            json.dumps(serializable_state)
        )
    
    # Update database (persistence)
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE chat_session
                SET summary = %s, summary_count = %s, updated_at = %s
                WHERE session_id = %s
            """, (
                summary_state['previous_summary'],
                summary_state['summarized_count'],
                summary_state['last_updated'],
                session_id
            ))
        conn.commit()
    except Exception as e:
        print(f"Error updating summary state in DB: {e}")
        conn.rollback()
    finally:
        pool.putconn(conn)


def get_summary_state(session_id: str) -> Dict:
    """Get summary state from Redis with fallback to database"""
    # Try Redis first (fast)
    if redis_client:
        redis_key = f"chat:summary_state:{session_id}"
        cached_state = safe_redis_operation(redis_client.get, redis_key)
        
        if cached_state:
            try:
                state = json.loads(cached_state)
                # Convert ISO string back to datetime if needed
                if state.get('last_updated'):
                    state['last_updated'] = datetime.fromisoformat(state['last_updated'])
                return state
            except (json.JSONDecodeError, ValueError):
                pass
    
    # Fallback to database
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT summary, summary_count, updated_at FROM chat_session WHERE session_id = %s",
                (session_id,)
            )
            row = cur.fetchone()
            
            if row and row[0]:  # summary exists
                state = {
                    'previous_summary': row[0],
                    'summarized_count': row[1] or 0,
                    'last_updated': row[2]
                }
                # Cache in Redis for next time
                cache_summary_state(session_id, state)
                return state
    except Exception as e:
        print(f"Error fetching summary state from DB: {e}")
    finally:
        pool.putconn(conn)
    
    # Return empty state for new sessions
    return {
        'previous_summary': None,
        'summarized_count': 0,
        'last_updated': None
    }


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


async def get_semantic_cached_response(message: str) -> Optional[str]:
    """Check semantic cache for similar questions"""
    if not llmcache:
        return None
    
    try:
        results = llmcache.check(
            prompt=message,
            num_results=1,
            return_fields=["prompt", "response"]
        )
        
        if results:
            best_match = results[0]
            vector_distance = best_match.get("vector_distance")
            cached_prompt = best_match.get("prompt", "")
            cached_response = best_match.get("response", "")
            
            if cached_response:
                print("✅ Semantic cache hit!")
                print(f"   User query:   {message[:60]}...")
                print(f"   Cached query: {cached_prompt[:60]}...")
                
                if vector_distance is not None:
                    print(f"   Distance: {vector_distance:.4f}")
                else:
                    print("   Distance: N/A")
                
                return cached_response
        
        print("❌ No semantic cache match")
        return None
        
    except Exception as e:
        print(f"⚠️ Semantic cache lookup error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def save_to_semantic_cache(message: str, response: str) -> bool:
    """Save question-response pair to semantic cache"""
    if not llmcache:
        return False
    
    try:
        llmcache.store(
            prompt=message,
            response=response
        )
        print(f"✅ Saved to semantic cache: {message[:60]}...")
        return True
        
    except Exception as e:
        print(f"⚠️ Semantic cache save error: {e}")
        return False
