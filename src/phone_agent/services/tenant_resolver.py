"""Tenant Resolver Service.

Identifies the correct tenant for incoming communications:
- Phone calls: Match by incoming phone number (dedicated lines)
- Emails: Match by recipient address or forwarding rules
- Webhooks: Match by API key or subdomain
- Web forms: Match by referrer domain or form ID
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from phone_agent.db.models.tenant import TenantModel
from phone_agent.db.repositories.tenant_repos import TenantRepository

logger = logging.getLogger(__name__)


@dataclass
class TenantResolution:
    """Result of tenant resolution."""

    tenant: TenantModel | None
    resolved: bool
    method: str  # How tenant was identified
    confidence: float  # 0.0-1.0
    message: str


class TenantResolver:
    """Service for identifying tenants from various sources.

    Supports multiple resolution methods:
    1. Phone number: Each tenant has dedicated phone numbers
    2. Email address: Match by To: address or domain
    3. Subdomain: Match by request hostname
    4. API key: Match by Bearer token
    5. Webhook signature: Match by signature secret

    Usage:
        resolver = TenantResolver(tenant_repo)

        # Resolve from phone call
        result = await resolver.resolve_from_phone("+49712345678")

        # Resolve from email
        result = await resolver.resolve_from_email("info@mueller-shk.de")

        # Resolve from subdomain
        result = await resolver.resolve_from_subdomain("mueller-shk.itf-handwerk.de")
    """

    def __init__(self, tenant_repo: TenantRepository):
        """Initialize resolver.

        Args:
            tenant_repo: Tenant repository for lookups
        """
        self.tenant_repo = tenant_repo

        # Cache for fast resolution
        self._phone_cache: dict[str, UUID] = {}
        self._email_cache: dict[str, UUID] = {}
        self._subdomain_cache: dict[str, UUID] = {}

    async def resolve_from_phone(
        self,
        phone_number: str,
        fallback_tenant_id: UUID | None = None,
    ) -> TenantResolution:
        """Resolve tenant from incoming phone number.

        Args:
            phone_number: Incoming phone number (E.164 format preferred)
            fallback_tenant_id: Optional fallback tenant ID

        Returns:
            TenantResolution with tenant or None
        """
        # Normalize phone number
        normalized = self._normalize_phone(phone_number)

        # Check cache
        if normalized in self._phone_cache:
            tenant_id = self._phone_cache[normalized]
            tenant = await self.tenant_repo.get(tenant_id)
            if tenant:
                return TenantResolution(
                    tenant=tenant,
                    resolved=True,
                    method="phone_cache",
                    confidence=1.0,
                    message=f"Resolved from cached phone: {normalized}",
                )

        # Query by phone number
        tenant = await self.tenant_repo.get_by_phone(normalized)

        if tenant:
            # Cache for future lookups
            self._phone_cache[normalized] = tenant.id
            return TenantResolution(
                tenant=tenant,
                resolved=True,
                method="phone_lookup",
                confidence=1.0,
                message=f"Resolved from phone: {normalized} → {tenant.name}",
            )

        # Try fallback
        if fallback_tenant_id:
            tenant = await self.tenant_repo.get(fallback_tenant_id)
            if tenant:
                return TenantResolution(
                    tenant=tenant,
                    resolved=True,
                    method="fallback",
                    confidence=0.5,
                    message=f"Fallback to configured tenant: {tenant.name}",
                )

        return TenantResolution(
            tenant=None,
            resolved=False,
            method="none",
            confidence=0.0,
            message=f"Could not resolve tenant for phone: {phone_number}",
        )

    async def resolve_from_email(
        self,
        email_address: str,
        sender_email: str | None = None,
    ) -> TenantResolution:
        """Resolve tenant from email address.

        Checks in order:
        1. Exact To: address match in tenant configuration
        2. Domain match (e.g., *@mueller-shk.de)
        3. Sender's email domain match (for replies)

        Args:
            email_address: Recipient email address (To:)
            sender_email: Optional sender email (From:)

        Returns:
            TenantResolution with tenant or None
        """
        email_lower = email_address.lower()
        domain = email_lower.split("@")[-1] if "@" in email_lower else None

        # Check cache
        if email_lower in self._email_cache:
            tenant_id = self._email_cache[email_lower]
            tenant = await self.tenant_repo.get(tenant_id)
            if tenant:
                return TenantResolution(
                    tenant=tenant,
                    resolved=True,
                    method="email_cache",
                    confidence=1.0,
                    message=f"Resolved from cached email: {email_lower}",
                )

        # Query all active tenants and check email configuration
        tenants = await self.tenant_repo.get_active_tenants()

        for tenant in tenants:
            # Check tenant's email
            if tenant.email and tenant.email.lower() == email_lower:
                self._email_cache[email_lower] = tenant.id
                return TenantResolution(
                    tenant=tenant,
                    resolved=True,
                    method="email_exact",
                    confidence=1.0,
                    message=f"Resolved from email: {email_lower} → {tenant.name}",
                )

            # Check domain in settings
            settings = tenant.settings_json or {}
            email_config = settings.get("email_intake", {})

            # Check configured email addresses
            if email_config.get("imap_user", "").lower() == email_lower:
                self._email_cache[email_lower] = tenant.id
                return TenantResolution(
                    tenant=tenant,
                    resolved=True,
                    method="email_config",
                    confidence=1.0,
                    message=f"Resolved from email config: {email_lower} → {tenant.name}",
                )

            # Check allowed domains
            allowed_domains = email_config.get("allowed_domains", [])
            if domain and domain in allowed_domains:
                self._email_cache[email_lower] = tenant.id
                return TenantResolution(
                    tenant=tenant,
                    resolved=True,
                    method="email_domain",
                    confidence=0.9,
                    message=f"Resolved from domain: {domain} → {tenant.name}",
                )

        return TenantResolution(
            tenant=None,
            resolved=False,
            method="none",
            confidence=0.0,
            message=f"Could not resolve tenant for email: {email_address}",
        )

    async def resolve_from_subdomain(
        self,
        hostname: str,
    ) -> TenantResolution:
        """Resolve tenant from request hostname/subdomain.

        Args:
            hostname: Full hostname (e.g., "mueller-shk.itf-handwerk.de")

        Returns:
            TenantResolution with tenant or None
        """
        # Extract subdomain
        parts = hostname.lower().split(".")
        if len(parts) < 2:
            return TenantResolution(
                tenant=None,
                resolved=False,
                method="invalid_hostname",
                confidence=0.0,
                message=f"Invalid hostname format: {hostname}",
            )

        # First part is subdomain (e.g., "mueller-shk")
        subdomain = parts[0]

        # Skip common subdomains
        if subdomain in ("www", "api", "app", "dashboard", "admin"):
            return TenantResolution(
                tenant=None,
                resolved=False,
                method="system_subdomain",
                confidence=0.0,
                message=f"System subdomain, not tenant: {subdomain}",
            )

        # Check cache
        if subdomain in self._subdomain_cache:
            tenant_id = self._subdomain_cache[subdomain]
            tenant = await self.tenant_repo.get(tenant_id)
            if tenant:
                return TenantResolution(
                    tenant=tenant,
                    resolved=True,
                    method="subdomain_cache",
                    confidence=1.0,
                    message=f"Resolved from cached subdomain: {subdomain}",
                )

        # Query by subdomain
        tenant = await self.tenant_repo.get_by_subdomain(subdomain)

        if tenant:
            self._subdomain_cache[subdomain] = tenant.id
            return TenantResolution(
                tenant=tenant,
                resolved=True,
                method="subdomain_lookup",
                confidence=1.0,
                message=f"Resolved from subdomain: {subdomain} → {tenant.name}",
            )

        return TenantResolution(
            tenant=None,
            resolved=False,
            method="none",
            confidence=0.0,
            message=f"Could not resolve tenant for subdomain: {subdomain}",
        )

    async def resolve_from_api_key(
        self,
        api_key: str,
    ) -> TenantResolution:
        """Resolve tenant from API key.

        Args:
            api_key: API key from request header

        Returns:
            TenantResolution with tenant or None
        """
        # Query all active tenants and check API keys
        tenants = await self.tenant_repo.get_active_tenants()

        for tenant in tenants:
            settings = tenant.settings_json or {}
            stored_key = settings.get("api_key")

            if stored_key and stored_key == api_key:
                return TenantResolution(
                    tenant=tenant,
                    resolved=True,
                    method="api_key",
                    confidence=1.0,
                    message=f"Resolved from API key → {tenant.name}",
                )

        return TenantResolution(
            tenant=None,
            resolved=False,
            method="none",
            confidence=0.0,
            message="Could not resolve tenant from API key",
        )

    async def resolve(
        self,
        phone: str | None = None,
        email: str | None = None,
        subdomain: str | None = None,
        api_key: str | None = None,
        fallback_tenant_id: UUID | None = None,
    ) -> TenantResolution:
        """Try multiple resolution methods in order.

        Args:
            phone: Optional phone number
            email: Optional email address
            subdomain: Optional subdomain/hostname
            api_key: Optional API key
            fallback_tenant_id: Optional fallback tenant

        Returns:
            Best TenantResolution found
        """
        # Try each method in priority order
        if api_key:
            result = await self.resolve_from_api_key(api_key)
            if result.resolved:
                return result

        if subdomain:
            result = await self.resolve_from_subdomain(subdomain)
            if result.resolved:
                return result

        if phone:
            result = await self.resolve_from_phone(phone, fallback_tenant_id)
            if result.resolved:
                return result

        if email:
            result = await self.resolve_from_email(email)
            if result.resolved:
                return result

        # Try fallback
        if fallback_tenant_id:
            tenant = await self.tenant_repo.get(fallback_tenant_id)
            if tenant:
                return TenantResolution(
                    tenant=tenant,
                    resolved=True,
                    method="fallback",
                    confidence=0.5,
                    message=f"Used fallback tenant: {tenant.name}",
                )

        return TenantResolution(
            tenant=None,
            resolved=False,
            method="none",
            confidence=0.0,
            message="Could not resolve tenant from any method",
        )

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to E.164 format.

        Args:
            phone: Phone number in any format

        Returns:
            Normalized phone number
        """
        # Remove all non-digit characters except leading +
        cleaned = "".join(c for c in phone if c.isdigit() or c == "+")

        # Ensure E.164 format for German numbers
        if cleaned.startswith("0"):
            # German national format → E.164
            cleaned = "+49" + cleaned[1:]
        elif cleaned.startswith("49") and not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        elif not cleaned.startswith("+"):
            # Assume German number
            cleaned = "+49" + cleaned

        return cleaned

    def clear_cache(self) -> None:
        """Clear all resolution caches."""
        self._phone_cache.clear()
        self._email_cache.clear()
        self._subdomain_cache.clear()
        logger.info("Tenant resolver cache cleared")

    async def warm_cache(self) -> int:
        """Pre-populate cache with all active tenants.

        Returns:
            Number of tenants cached
        """
        tenants = await self.tenant_repo.get_active_tenants()
        count = 0

        for tenant in tenants:
            # Cache phone
            if tenant.phone:
                normalized = self._normalize_phone(tenant.phone)
                self._phone_cache[normalized] = tenant.id
                count += 1

            # Cache subdomain
            if tenant.subdomain:
                self._subdomain_cache[tenant.subdomain.lower()] = tenant.id
                count += 1

            # Cache email
            if tenant.email:
                self._email_cache[tenant.email.lower()] = tenant.id
                count += 1

        logger.info(f"Warmed tenant resolver cache: {count} entries")
        return count
