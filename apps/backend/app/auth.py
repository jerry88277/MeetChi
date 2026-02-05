"""
MeetChi Backend Authentication Module

This module provides Google OAuth token verification for protecting API endpoints.
It validates access tokens issued by NextAuth.js frontend against Google's OAuth servers.

Usage:
    from app.auth import get_current_user, get_optional_user
    
    @app.get("/protected")
    async def protected_route(user: dict = Depends(get_current_user)):
        return {"message": f"Hello {user['email']}"}
    
    @app.get("/optional-protected")
    async def optional_protected(user: dict = Depends(get_optional_user)):
        if user:
            return {"message": f"Hello {user['email']}"}
        return {"message": "Hello guest"}
"""

import os
import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

logger = logging.getLogger(__name__)

# Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"

# Security scheme
security = HTTPBearer(auto_error=False)


async def verify_google_token(token: str) -> Optional[dict]:
    """
    Verify a Google OAuth ID token.
    
    Args:
        token: The ID token from Google OAuth
        
    Returns:
        User info dict if valid, None otherwise
    """
    try:
        # Verify the token with Google
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
        
        # Verify issuer
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            logger.warning(f"Invalid issuer: {idinfo['iss']}")
            return None
        
        # Extract user info
        return {
            "id": idinfo.get("sub"),
            "email": idinfo.get("email"),
            "name": idinfo.get("name"),
            "picture": idinfo.get("picture"),
            "email_verified": idinfo.get("email_verified", False)
        }
        
    except ValueError as e:
        logger.warning(f"Token verification failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}")
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Dependency to get the current authenticated user.
    Raises 401 if not authenticated.
    
    In development mode (AUTH_REQUIRED=false), returns a mock user.
    """
    # Development mode: skip authentication
    if not AUTH_REQUIRED:
        logger.debug("Auth bypass: AUTH_REQUIRED=false")
        return {
            "id": "dev-user",
            "email": "dev@example.com",
            "name": "Development User",
            "picture": None,
            "email_verified": True
        }
    
    # Production mode: require authentication
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user = await verify_google_token(credentials.credentials)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """
    Dependency to get the current user if authenticated, None otherwise.
    Does not raise an error if not authenticated.
    """
    if not credentials:
        return None
    
    return await verify_google_token(credentials.credentials)


# Email whitelist for admin functions (MVP)
ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "").split(",")


async def get_admin_user(
    user: dict = Depends(get_current_user)
) -> dict:
    """
    Dependency to verify the user is an admin.
    """
    if user["email"] not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user
