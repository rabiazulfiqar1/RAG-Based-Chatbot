"""
Centralized connection management for database, Redis, LLM, and vector store.
"""

import os
import redis
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from langchain_groq import ChatGroq
from redisvl.extensions.cache.llm import SemanticCache
from redisvl.utils.vectorize import HFTextVectorizer

from app.core.constants import MAX_RETRIES

load_dotenv()

# Database Connection Pool
pool = ConnectionPool(
    os.getenv("SUPABASE_DB_URL"),
    max_size=20,
    min_size=1
)

# Redis Connection
redis_client = None
try:
    redis_client = redis.from_url(
        os.getenv("REDIS_URL"),
        decode_responses=True
    )
    redis_client.ping()
    print("✅ Redis connected successfully")
except Exception as e:
    print(f"❌ Redis connection failed: {e}")
    redis_client = None

# LLM Model
llm = ChatGroq(
    model="llama-3.1-8b-instant",
    groq_api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.4,
    max_retries=MAX_RETRIES,
    max_tokens=1024,
    streaming=True
)

# Embeddings Model
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-mpnet-base-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)

# Semantic Cache
llmcache = None
if redis_client:
    try:
        llmcache = SemanticCache(
            name="chat_semantic_cache",
            redis_url=os.getenv("REDIS_URL"),
            distance_threshold=0.2,
            ttl=3600 * 24 * 60,
            vectorizer=HFTextVectorizer(
                model="sentence-transformers/all-mpnet-base-v2"
            )
        )
        print("✅ RedisVL SemanticCache initialized")
    except Exception as e:
        print(f"❌ SemanticCache initialization failed: {e}")
        llmcache = None

# Document Vector Store
document_vector_store = PGVector(
    embeddings=embeddings,
    collection_name="user_documents",
    connection=os.getenv("SUPABASE_DB_URL"),
    use_jsonb=True,
)
