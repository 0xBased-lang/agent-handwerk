"""API routers and authentication.

Multi-tenant authentication exports:
- TenantContext: Tenant context model for API requests
- get_tenant_context: Dependency for tenant-scoped endpoints
- get_optional_tenant_context: Dependency for mixed auth endpoints
- require_tenant_admin: Dependency requiring admin role
- require_tenant_worker: Dependency requiring worker role
- require_industry: Factory for industry-specific dependencies
"""

from phone_agent.api.auth import (
    # Core auth
    AuthenticatedUser,
    TokenPayload,
    TenantContext,
    create_access_token,
    decode_token,
    get_current_user,
    get_optional_user,
    # Scope-based auth
    require_scope,
    require_admin,
    require_write,
    require_read,
    # Multi-tenant auth
    get_tenant_context,
    get_optional_tenant_context,
    require_tenant_role,
    require_industry,
    require_tenant_admin,
    require_tenant_worker,
    require_healthcare,
    require_handwerk,
    require_gastro,
    require_professional,
)

__all__ = [
    # Core auth
    "AuthenticatedUser",
    "TokenPayload",
    "TenantContext",
    "create_access_token",
    "decode_token",
    "get_current_user",
    "get_optional_user",
    # Scope-based auth
    "require_scope",
    "require_admin",
    "require_write",
    "require_read",
    # Multi-tenant auth
    "get_tenant_context",
    "get_optional_tenant_context",
    "require_tenant_role",
    "require_industry",
    "require_tenant_admin",
    "require_tenant_worker",
    "require_healthcare",
    "require_handwerk",
    "require_gastro",
    "require_professional",
]
