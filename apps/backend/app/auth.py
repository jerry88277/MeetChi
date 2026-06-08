"""
MeetChi Backend Authentication Module

Supports two OAuth providers:
  - Google   : id_token issued by Google OAuth (accounts.google.com)
  - Microsoft: id_token issued by Microsoft Entra ID (login.microsoftonline.com)
  - UAT      : HS256 token signed by MeetChi frontend with AUTH_SECRET (UAT only)

Provider is auto-detected from the JWT `iss` claim — no extra header needed.
If neither MS_CLIENT_ID nor GOOGLE_CLIENT_ID is configured, the module still
works in dev mode (AUTH_REQUIRED=false).

Usage:
    from app.auth import get_current_user, get_optional_user

    @app.get("/protected")
    async def protected_route(user: dict = Depends(get_current_user)):
        return {"message": f"Hello {user['email']}"}
"""

import os
import time
import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import httpx
from jose import jwt as jose_jwt
from jose.exceptions import JWTError, ExpiredSignatureError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"

# Microsoft Entra ID — populated once Azure AD App registration is complete
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "")
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "common")  # use tenant UUID for single-tenant

# Restrict sign-in to a specific email domain (e.g. "chimei.com.tw")
AUTH_ALLOWED_DOMAIN = os.getenv("AUTH_ALLOWED_DOMAIN", "")

# UAT mode: shared secret with NextAuth frontend (AUTH_SECRET env var)
# When UAT_ENABLED=true on frontend, it mints HS256 tokens with iss="meetchi-uat"
# Backend verifies them with this same secret.
AUTH_SECRET = os.getenv("AUTH_SECRET", "")

security = HTTPBearer(auto_error=False)

# ── Microsoft JWKS cache ──────────────────────────────────────────────────────

_ms_jwks_cache: Optional[dict] = None
_ms_jwks_expiry: float = 0.0
_JWKS_CACHE_TTL = 3600  # 1 hour


async def _get_ms_jwks() -> dict:
    """Fetch and cache Microsoft Entra ID JWKS keys."""
    global _ms_jwks_cache, _ms_jwks_expiry
    if _ms_jwks_cache and time.time() < _ms_jwks_expiry:
        return _ms_jwks_cache
    jwks_url = f"https://login.microsoftonline.com/{MS_TENANT_ID}/discovery/v2.0/keys"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
    _ms_jwks_cache = resp.json()
    _ms_jwks_expiry = time.time() + _JWKS_CACHE_TTL
    logger.debug(f"MS JWKS refreshed ({len(_ms_jwks_cache.get('keys', []))} keys)")
    return _ms_jwks_cache


# ── Provider detection ────────────────────────────────────────────────────────

def _peek_token_provider(token: str) -> str:
    """
    Decode JWT payload without signature verification to determine the provider.
    Returns "microsoft", "uat", or "google".
    """
    try:
        claims = jose_jwt.get_unverified_claims(token)
        iss = claims.get("iss", "")
        if "microsoftonline.com" in iss:
            return "microsoft"
        if iss == "meetchi-uat":
            return "uat"
    except Exception:
        pass
    return "google"


# ── Google verification ───────────────────────────────────────────────────────

async def verify_google_token(token: str) -> Optional[dict]:
    """Verify a Google OAuth ID token."""
    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID if GOOGLE_CLIENT_ID else None,
        )
        if idinfo["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
            logger.warning(f"Invalid Google token issuer: {idinfo['iss']}")
            return None
        return {
            "id": idinfo.get("sub"),
            "email": idinfo.get("email"),
            "name": idinfo.get("name"),
            "picture": idinfo.get("picture"),
            "email_verified": idinfo.get("email_verified", False),
            "provider": "google",
        }
    except ValueError as e:
        logger.warning(f"Google token verification failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during Google token verification: {e}")
        return None


# ── Microsoft verification ────────────────────────────────────────────────────

async def verify_microsoft_token(token: str) -> Optional[dict]:
    """
    Verify a Microsoft Entra ID (Azure AD) ID token using JWKS.

    Requires MS_CLIENT_ID env var (= Azure App client ID / Application ID).
    Optionally MS_TENANT_ID (defaults to "common" for multi-tenant).

    Returns None and logs a warning if MS_CLIENT_ID is not configured
    so the error is informative rather than silent during development.
    """
    if not MS_CLIENT_ID:
        logger.warning(
            "MS_CLIENT_ID not configured — Microsoft auth is disabled. "
            "Set MS_CLIENT_ID once Azure AD App registration is complete."
        )
        return None
    try:
        jwks = await _get_ms_jwks()

        # verify_iss=False → check issuer manually below (handles multi-tenant edge case)
        payload = jose_jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=MS_CLIENT_ID,
            options={"verify_iss": False},
        )

        # Enforce tenant-specific issuer for single-tenant deployments
        if MS_TENANT_ID != "common":
            expected_iss = f"https://login.microsoftonline.com/{MS_TENANT_ID}/v2.0"
            if payload.get("iss") != expected_iss:
                logger.warning(
                    f"MS token issuer mismatch: got {payload.get('iss')!r}, "
                    f"expected {expected_iss!r}"
                )
                return None

        email = (
            payload.get("preferred_username")
            or payload.get("email")
            or payload.get("upn", "")
        )
        return {
            "id": payload.get("oid") or payload.get("sub"),
            "email": email,
            "name": payload.get("name"),
            "picture": None,
            "email_verified": True,  # MS Entra ID tokens are always email-verified
            "provider": "microsoft",
        }
    except ExpiredSignatureError:
        logger.warning("MS token expired")
        return None
    except JWTError as e:
        logger.warning(f"MS token verification failed: {e}")
        return None
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch MS JWKS: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during MS token verification: {e}")
        return None


# ── UAT verification ──────────────────────────────────────────────────────────

async def verify_uat_token(token: str) -> Optional[dict]:
    """
    Verify a UAT HS256 token minted by the MeetChi frontend.

    The frontend signs this token with AUTH_SECRET when a user logs in via
    the Credentials provider (UAT_ENABLED=true).  The token carries:
      iss: "meetchi-uat"
      sub / email / name from the UAT_USERS env list.

    This path is ONLY active when AUTH_SECRET is configured on the backend.
    UAT tokens are intentionally short-lived (8h) and bypass domain restriction.
    """
    if not AUTH_SECRET:
        logger.warning("UAT token received but AUTH_SECRET is not set on backend")
        return None
    try:
        payload = jose_jwt.decode(token, AUTH_SECRET, algorithms=["HS256"])
        if payload.get("iss") != "meetchi-uat":
            logger.warning(f"UAT token has unexpected iss: {payload.get('iss')}")
            return None
        email = payload.get("email", "")
        return {
            "id": payload.get("sub", email),
            "email": email,
            "name": payload.get("name", "UAT User"),
            "picture": None,
            "email_verified": True,
            "provider": "uat",
        }
    except ExpiredSignatureError:
        logger.warning("UAT token expired")
        return None
    except JWTError as e:
        logger.warning(f"UAT token verification failed: {e}")
        return None


# ── Domain restriction ────────────────────────────────────────────────────────

def _check_allowed_domain(user: dict) -> bool:
    """
    If AUTH_ALLOWED_DOMAIN is set, only allow emails from that domain.
    e.g. AUTH_ALLOWED_DOMAIN=chimei.com.tw → only @chimei.com.tw users pass.
    UAT users (provider="uat") bypass domain restriction intentionally.
    """
    if not AUTH_ALLOWED_DOMAIN:
        return True
    # UAT users bypass domain restriction (they may use non-chimei test emails)
    if user.get("provider") == "uat":
        return True
    email = user.get("email", "") or ""
    return email.lower().endswith(f"@{AUTH_ALLOWED_DOMAIN.lower()}")


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    Dependency to get the current authenticated user.
    Raises 401 if not authenticated.

    - Development mode (AUTH_REQUIRED=false): returns a mock user
    - Production: verifies Google or MS token based on `iss` claim
    """
    if not AUTH_REQUIRED:
        logger.debug("Auth bypass: AUTH_REQUIRED=false")
        return {
            "id": "dev-user",
            "email": "dev@example.com",
            "name": "Development User",
            "picture": None,
            "email_verified": True,
            "provider": "dev",
        }

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # E2E test mode
    is_e2e_mode = os.getenv("NEXT_PUBLIC_E2E_TEST_MODE", "false").lower() == "true"
    if is_e2e_mode and credentials.credentials == "mock_id_token_for_e2e_testing":
        logger.debug("Auth bypass: E2E Test Mode active with mock token")
        return {
            "id": "test_e2e_user_123",
            "email": "test@example.com",
            "name": "E2E Test User",
            "picture": None,
            "email_verified": True,
            "provider": "e2e",
        }

    # Auto-detect provider from JWT iss claim
    provider = _peek_token_provider(credentials.credentials)
    if provider == "microsoft":
        user = await verify_microsoft_token(credentials.credentials)
    elif provider == "uat":
        user = await verify_uat_token(credentials.credentials)
    else:
        user = await verify_google_token(credentials.credentials)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not _check_allowed_domain(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access restricted to @{AUTH_ALLOWED_DOMAIN} accounts",
        )

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Dependency to get the current user if authenticated, None otherwise."""
    if not credentials:
        return None
    provider = _peek_token_provider(credentials.credentials)
    if provider == "microsoft":
        return await verify_microsoft_token(credentials.credentials)
    return await verify_google_token(credentials.credentials)


# Email whitelist for admin functions (MVP)
ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "").split(",")


async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    """Dependency to verify the user is an admin."""
    if user["email"] not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user

