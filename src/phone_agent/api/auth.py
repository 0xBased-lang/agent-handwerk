"""JWT Authentication for API endpoints.

Provides JWT-based authentication for securing API endpoints.
Webhooks remain unauthenticated but use signature validation.

Multi-tenant Support:
- tenant_id is included in JWT tokens
- TenantContext provides tenant info for API dependencies
- Industry-specific prompts are loaded based on tenant configuration
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from phone_agent.config import get_settings


# HTTP Bearer security scheme
security = HTTPBearer(auto_error=False)
security_required = HTTPBearer(auto_error=True)


class TokenPayload(BaseModel):
    """JWT token payload with multi-tenant support."""

    sub: str  # Subject (user/device ID)
    exp: datetime  # Expiration time
    iat: datetime  # Issued at
    type: str = "access"  # Token type
    scopes: list[str] = []  # Permission scopes
    tenant_id: str | None = None  # Tenant UUID (multi-tenant support)
    industry: str | None = None  # Industry vertical (gesundheit, handwerk, etc.)
    role: str | None = None  # User role within tenant (admin, worker, viewer)


class AuthenticatedUser(BaseModel):
    """Authenticated user/device information with tenant context."""

    id: str
    scopes: list[str] = []
    token_type: str = "access"
    tenant_id: str | None = None  # Tenant UUID
    industry: str | None = None  # Industry vertical
    role: str | None = None  # Role within tenant


class TenantContext(BaseModel):
    """Tenant context for API requests.

    Provides all tenant-related information needed for request processing:
    - Tenant identification
    - Industry-specific configuration
    - User role and permissions
    """

    tenant_id: UUID
    industry: str  # gesundheit, handwerk, gastro, freie_berufe
    user_id: str
    role: str = "worker"  # admin, worker, viewer
    scopes: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic config."""
        frozen = True  # Immutable after creation


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
    tenant_id: str | None = None,
    industry: str | None = None,
    role: str | None = None,
) -> str:
    """Create a new JWT access token with optional tenant context.

    Args:
        subject: The subject (user/device ID) for the token
        scopes: List of permission scopes
        expires_delta: Optional custom expiration time
        tenant_id: Optional tenant UUID for multi-tenant access
        industry: Optional industry vertical (gesundheit, handwerk, etc.)
        role: Optional role within tenant (admin, worker, viewer)

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

    # Add tenant context if provided
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if industry:
        payload["industry"] = industry
    if role:
        payload["role"] = role

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
            return {"user_id": user.id, "tenant_id": user.tenant_id}
    """
    payload = decode_token(credentials.credentials)

    return AuthenticatedUser(
        id=payload.sub,
        scopes=payload.scopes,
        token_type=payload.type,
        tenant_id=payload.tenant_id,
        industry=payload.industry,
        role=payload.role,
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
                return {"user_id": user.id, "tenant_id": user.tenant_id}
            return {"message": "Anonymous access"}
    """
    if credentials is None:
        return None

    payload = decode_token(credentials.credentials)

    return AuthenticatedUser(
        id=payload.sub,
        scopes=payload.scopes,
        token_type=payload.type,
        tenant_id=payload.tenant_id,
        industry=payload.industry,
        role=payload.role,
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


# ============================================================================
# Multi-Tenant Dependencies
# ============================================================================


async def get_tenant_context(
    user: AuthenticatedUser = Depends(get_current_user),
) -> TenantContext:
    """Dependency to get tenant context from authenticated user.

    Requires that the user's token contains tenant_id and industry.
    Use this for endpoints that require tenant-scoped operations.

    Usage:
        @router.get("/tenant-resource")
        async def tenant_endpoint(
            tenant: TenantContext = Depends(get_tenant_context)
        ):
            return {"tenant_id": str(tenant.tenant_id)}

    Raises:
        HTTPException 403: If user token doesn't contain tenant context
    """
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required. Token must include tenant_id.",
        )

    if not user.industry:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Industry context required. Token must include industry.",
        )

    try:
        tenant_uuid = UUID(user.tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant_id format. Must be a valid UUID.",
        )

    return TenantContext(
        tenant_id=tenant_uuid,
        industry=user.industry,
        user_id=user.id,
        role=user.role or "worker",
        scopes=user.scopes,
    )


async def get_optional_tenant_context(
    user: AuthenticatedUser | None = Depends(get_optional_user),
) -> TenantContext | None:
    """Dependency to optionally get tenant context.

    Returns None if no token provided or token lacks tenant context.
    Use for endpoints that work both with and without tenant context.

    Usage:
        @router.get("/mixed-endpoint")
        async def mixed_endpoint(
            tenant: TenantContext | None = Depends(get_optional_tenant_context)
        ):
            if tenant:
                return {"tenant_id": str(tenant.tenant_id)}
            return {"message": "No tenant context"}
    """
    if user is None or not user.tenant_id or not user.industry:
        return None

    try:
        tenant_uuid = UUID(user.tenant_id)
    except ValueError:
        return None

    return TenantContext(
        tenant_id=tenant_uuid,
        industry=user.industry,
        user_id=user.id,
        role=user.role or "worker",
        scopes=user.scopes,
    )


def require_tenant_role(required_role: str):
    """Create a dependency that requires a specific tenant role.

    Usage:
        @router.post("/admin-only")
        async def admin_endpoint(
            tenant: TenantContext = Depends(require_tenant_role("admin"))
        ):
            return {"message": "Admin access granted"}
    """
    async def role_checker(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        # Role hierarchy: admin > worker > viewer
        role_hierarchy = {"admin": 3, "worker": 2, "viewer": 1}
        user_level = role_hierarchy.get(tenant.role, 0)
        required_level = role_hierarchy.get(required_role, 99)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required. Current role: '{tenant.role}'",
            )
        return tenant

    return role_checker


def require_industry(allowed_industries: list[str]):
    """Create a dependency that requires specific industry.

    Usage:
        @router.get("/healthcare-only")
        async def healthcare_endpoint(
            tenant: TenantContext = Depends(require_industry(["gesundheit"]))
        ):
            return {"industry": tenant.industry}
    """
    async def industry_checker(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        if tenant.industry not in allowed_industries:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Industry must be one of: {allowed_industries}. Current: '{tenant.industry}'",
            )
        return tenant

    return industry_checker


# Convenience dependencies for common roles
require_tenant_admin = require_tenant_role("admin")
require_tenant_worker = require_tenant_role("worker")

# Industry-specific dependencies
require_healthcare = require_industry(["gesundheit"])
require_handwerk = require_industry(["handwerk"])
require_gastro = require_industry(["gastro"])
require_professional = require_industry(["freie_berufe"])
