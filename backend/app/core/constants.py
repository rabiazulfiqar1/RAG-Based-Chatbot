"""
Configuration constants for the RAG chatbot backend.
"""

# Message and cache configuration
RECENT_MESSAGES_COUNT = 5
SUMMARY_BATCH_SIZE = 5
TOTAL_CACHE_SIZE = RECENT_MESSAGES_COUNT + SUMMARY_BATCH_SIZE

# Redis TTL (time to live)
REDIS_TTL = 3600 * 24 * 7  # 7 days

# LLM configuration
MAX_RETRIES = 3

# Document chunking configuration
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Maximum documents allowed per session
MAX_DOCUMENTS_PER_SESSION = 10