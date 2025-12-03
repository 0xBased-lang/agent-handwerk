"""JWT Authentication for API endpoints.

Provides JWT-based authentication for securing API endpoints.
Webhooks remain unauthenticated but use signature validation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from phone_agent.config import get_settings


# HTTP Bearer security scheme
security = HTTPBearer(auto_error=False)
security_required = HTTPBearer(auto_error=True)


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # Subject (user/device ID)
    exp: datetime  # Expiration time
    iat: datetime  # Issued at
    type: str = "access"  # Token type
    scopes: list[str] = []  # Permission scopes


class AuthenticatedUser(BaseModel):
    """Authenticated user/device information."""

    id: str
    scopes: list[str] = []
    token_type: str = "access"


def get_secret_key() -> str:
    """Get JWT secret key from settings.

    Raises:
        ValueError: If no secret key is configured in production environment.
    """
    settings = get_settings()
    secret = getattr(settings, "jwt_secret_key", None) or getattr(settings, "secret_key", None)

    if not secret:
        env = getattr(settings, "environment", "development")
        if env in ("production", "staging", "prod"):
            raise ValueError(
                "JWT secret key must be configured in production! "
                "Set ITF_JWT_SECRET_KEY environment variable."
            )
        # Development-only fallback with warning
        import warnings
        warnings.warn(
            "Using insecure default JWT secret. "
            "Set ITF_JWT_SECRET_KEY for production!",
            RuntimeWarning,
            stacklevel=2,
        )
        secret = "INSECURE-DEV-SECRET-DO-NOT-USE-IN-PRODUCTION"

    return secret


def get_algorithm() -> str:
    """Get JWT algorithm."""
    return "HS256"


def create_access_token(
    subject: str,
    scopes: list[str] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a new JWT access token.

    Args:
        subject: The subject (user/device ID) for the token
        scopes: List of permission scopes
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    settings = get_settings()

    if expires_delta is None:
        expires_delta = timedelta(
            minutes=getattr(settings, "jwt_expiry_minutes", 60)
        )

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": subject,
        "exp": expire,
        "iat": now,
        "type": "access",
        "scopes": scopes or [],
    }

    return jwt.encode(payload, get_secret_key(), algorithm=get_algorithm())


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token.

    Args:
        token: The JWT token string

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            get_secret_key(),
            algorithms=[get_algorithm()],
        )
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security_required),
) -> AuthenticatedUser:
    """Dependency to get the current authenticated user.

    This is a required authentication - fails if no token provided.

    Usage:
        @router.get("/protected")
        async def protected_endpoint(
            user: AuthenticatedUser = Depends(get_current_user)
        ):
            return {"user_id": user.id}
    """
    payload = decode_token(credentials.credentials)

    return AuthenticatedUser(
        id=payload.sub,
        scopes=payload.scopes,
        token_type=payload.type,
    )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> AuthenticatedUser | None:
    """Dependency to optionally get the current user.

    Returns None if no token is provided (for mixed auth endpoints).

    Usage:
        @router.get("/optional-auth")
        async def optional_auth_endpoint(
            user: AuthenticatedUser | None = Depends(get_optional_user)
        ):
            if user:
                return {"user_id": user.id}
            return {"message": "Anonymous access"}
    """
    if credentials is None:
        return None

    payload = decode_token(credentials.credentials)

    return AuthenticatedUser(
        id=payload.sub,
        scopes=payload.scopes,
        token_type=payload.type,
    )


def require_scope(required_scope: str):
    """Create a dependency that requires a specific scope.

    Usage:
        @router.post("/admin-only")
        async def admin_endpoint(
            user: AuthenticatedUser = Depends(require_scope("admin"))
        ):
            return {"message": "Admin access granted"}
    """
    async def scope_checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if required_scope not in user.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Scope '{required_scope}' required",
            )
        return user

    return scope_checker


# Convenience dependencies for common scopes
require_admin = require_scope("admin")
require_write = require_scope("write")
require_read = require_scope("read")
