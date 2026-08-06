"""
Centralized connection management for database, Redis, LLM, and vector store.
"""
import os
import redis
from dotenv import load_dotenv
from psycopg_pool import AsyncConnectionPool  
from langchain_postgres import PGVector
from langchain_groq import ChatGroq
from app.core.constants import MAX_RETRIES
import traceback
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

load_dotenv()

pool = AsyncConnectionPool(
    os.getenv("SUPABASE_DB_POOL_URL"),
    max_size=20,
    min_size=1,
    open=False, 
)

# Redis Connection
redis_client = None
try:
    redis_client = redis.Redis.from_url(
        os.getenv("REDIS_URL"),
        decode_responses=True
    )
    redis_client.ping()
    print("Redis connected successfully")
except Exception as e:
    print(f"Redis connection failed: {e}")
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

# Embeddings Model — NVIDIA NIM hosted endpoint 
embeddings = NVIDIAEmbeddings(
    model="nvidia/nv-embedqa-e5-v5",
    api_key=os.getenv("NVIDIA_API_KEY"),
    truncate="END",
)

nvidia_embeddings = NVIDIAEmbeddings(
    model="nvidia/nv-embedqa-e5-v5",
    api_key=os.getenv("NVIDIA_API_KEY"),
    truncate="END",
)

# Document Vector Store
document_vector_store = PGVector(
    embeddings=embeddings,
    collection_name="user_documents",
    connection=os.getenv("SUPABASE_DB_SQLALCHEMY_URL"),
    use_jsonb=True,
)
