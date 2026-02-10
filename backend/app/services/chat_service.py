"""
Chat service for conversation management and streaming responses.
"""

import json
import asyncio
from typing import Dict, Any, AsyncIterator, List
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.connections import llm, redis_client
from app.core.constants import SUMMARY_BATCH_SIZE
from app.utils.cache_service import (
    get_cached_recent_messages,
    get_summary_state,
    cache_summary_state
)
from app.utils.database_service import get_raw_message_history


# Chat Prompt Template
chat_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an AI mentor.
        For complex or multi-step problems (math, coding, logic), guide the student Socratically:
        ask questions, give hints, encourage reasoning, and adapt to their level.
        Do not reveal full solutions immediately.

        Exceptions:
        - Directly answer factual, definitional, or simple questions (e.g. "RLHF full form", "2+2", "111*111").
        - Give function names, syntax, tips, or advice directly when requested.

        Default: Mentor with questions + hints.
        If simple/obvious → answer directly. Adapt your guidance based on the student's current level of understanding.""",
    ),
    MessagesPlaceholder("chat_history"),
    ("user", "{message}")
])

# Chat Chain
chat_chain = chat_prompt | llm | StrOutputParser()


def get_conversation_context(session_id: str, K=5, SUMMARY_BATCH_SIZE=5):
    """
    Hierarchical summarization approach
    
    Logic:
    - Keep last K messages as raw
    - When total messages > K, maintain running summary
    - Only update summary every SUMMARY_BATCH_SIZE new messages
    - Always preserve previous summary context
    
    Optimized context retrieval:
    - Cache holds K + SUMMARY_BATCH_SIZE (10 total) messages
    - Use cached messages for both context and summarization
    - Minimal DB calls
    """
    
    # Get cached messages (up to 10: 5 recent + 5 summary batch)
    history_messages = get_cached_recent_messages(session_id, K=(K + SUMMARY_BATCH_SIZE))
    if not history_messages:
        # Cache miss - fallback to DB
        history_messages = get_raw_message_history(session_id, limit=(K + SUMMARY_BATCH_SIZE))
    
    # If we have fewer than K messages, just return all raw
    if len(history_messages) <= K:
        return history_messages
    
    # Get existing summary state
    summary_state = get_summary_state(session_id)
    
    # Return context: [summary] + [last K raw messages]
    context = []
    if summary_state.get('previous_summary'):
        context.append(SystemMessage(content=f"Conversation summary: {summary_state['previous_summary']}"))
    
    # Add last K raw messages
    context.extend(history_messages[-K:])
    
    return context


async def perform_background_summarization(
    session_id: str,
    cached_messages: List,
    K: int = 5,
    SUMMARY_BATCH_SIZE: int = 5
):
    """
    Background summarization using cached messages
    - Uses messages from cache (no DB calls for retrieval)
    - Runs asynchronously without blocking response
    - K: Number of recent messages to keep unsummarized
    - SUMMARY_BATCH_SIZE: Number of messages to summarize per batch
    """

    # If total messages in cache <= K, nothing to summarize
    total_messages = len(cached_messages)
    if total_messages <= K:
        print("⏸️ Not enough messages, all are recent K messages")
        return

    # How many messages are eligible to summarize (older than K)
    messages_eligible_for_summary = total_messages - K

    # Only summarize if we have a full batch
    if messages_eligible_for_summary < SUMMARY_BATCH_SIZE:
        print(f"⏸️ Not enough messages to summarize yet: {messages_eligible_for_summary} < {SUMMARY_BATCH_SIZE}")
        return

    # Slice exactly SUMMARY_BATCH_SIZE messages from oldest eligible
    messages_to_summarize = cached_messages[0:SUMMARY_BATCH_SIZE]
    if not messages_to_summarize:
        return

    print(f"📝 Summarizing {len(messages_to_summarize)} messages from cache for session {session_id}")

    # Get previous summary state
    summary_state = get_summary_state(session_id)
    previous_summary = summary_state.get('previous_summary', '')

    # Build summary prompt
    if previous_summary:
        summary_prompt = (
            f"Previous conversation summary: {previous_summary}\n\n"
            "Now summarize the following new messages and combine with the previous summary. "
            "Include specific details, key decisions, and important context:"
        )
    else:
        summary_prompt = (
            "Summarize the following conversation messages. "
            "Include specific details, key decisions, and important context:"
        )

    # Generate new summary asynchronously
    new_summary = await llm.ainvoke(
        messages_to_summarize + [HumanMessage(content=summary_prompt)]
    )

    # Update summary state
    new_summary_state = {
        'previous_summary': new_summary.content,
        'summarized_count': summary_state.get('summarized_count', 0) + len(messages_to_summarize),
        'last_updated': datetime.now()
    }
    cache_summary_state(session_id, new_summary_state)

    # Update cache: remove summarized messages, keep recent K
    if redis_client:
        redis_key = f"chat:recent_msgs:{session_id}"
        try:
            pipe = redis_client.pipeline()
            pipe.ltrim(redis_key, 0, K-1)  # Keep newest K messages
            pipe.execute()
        except Exception as e:
            print(f"Error trimming cache: {e}")

    print(f"✅ Background summarization completed for session {session_id}")


async def stream_llm_response(
    chain,
    input_data: Dict[str, Any]
) -> AsyncIterator[str]:
    """
    Stream LLM response token by token
    Yields each token as it's generated
    """
    try:
        async for chunk in chain.astream(input_data):
            if chunk:
                # Send token with SSE format
                yield f"data: {json.dumps({'token': chunk})}\n\n"
                
        # Send completion signal
        yield f"data: {json.dumps({'done': True})}\n\n"
        
    except Exception as e:
        error_msg = f"Error during streaming: {str(e)}"
        yield f"data: {json.dumps({'error': error_msg})}\n\n"