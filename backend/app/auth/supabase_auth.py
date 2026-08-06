from fastapi import HTTPException, Header
from supabase import create_client, Client
from typing import Dict, Any
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client with service role key
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("Missing Supabase configuration. Check your .env file.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

async def get_current_user(authorization: str = Header(None)) -> Dict[str, Any]:
    """Verify user token using Supabase"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    try:
        # Verify token with Supabase
        user_response = supabase.auth.get_user(token)
        
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        user = user_response.user
        
        return {
            "id": user.id,
            "email": user.email,
            "email_verified": user.email_confirmed_at is not None,
            "created_at": user.created_at,
            "last_sign_in": user.last_sign_in_at,
            "user_metadata": user.user_metadata or {}
        }
        
    except Exception as e:
        print(f"Authentication error: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed")