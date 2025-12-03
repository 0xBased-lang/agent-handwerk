"""Webhook security and signature verification.

Provides request signature validation for webhook endpoints to ensure
requests originate from legitimate sources (Twilio, sipgate, etc.).

Security measures:
- HMAC signature verification
- Timestamp validation (replay attack prevention)
- IP whitelist verification (optional)
- Trusted proxy validation for X-Forwarded-For
- Request body validation
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import time
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlencode

from itf_shared import get_logger

if TYPE_CHECKING:
    from fastapi import Request

log = get_logger(__name__)


def _is_ip_in_network(ip: str, networks: list[str]) -> bool:
    """Check if an IP address is in any of the given networks.

    Args:
        ip: IP address to check
        networks: List of IPs or CIDR ranges (e.g., ["127.0.0.1", "10.0.0.0/8"])

    Returns:
        True if IP is in any network
    """
    try:
        addr = ipaddress.ip_address(ip)
        for network in networks:
            try:
                if "/" in network:
                    # CIDR notation
                    if addr in ipaddress.ip_network(network, strict=False):
                        return True
                else:
                    # Single IP
                    if addr == ipaddress.ip_address(network):
                        return True
            except ValueError:
                continue
        return False
    except ValueError:
        return False


@dataclass
class WebhookSecurityConfig:
    """Webhook security configuration."""

    # Signature validation
    validate_signatures: bool = True

    # Twilio settings
    twilio_auth_token: str = ""
    twilio_signature_header: str = "X-Twilio-Signature"

    # sipgate settings
    sipgate_api_token: str = ""
    sipgate_signature_header: str = "X-Sipgate-Signature"

    # Generic HMAC settings
    hmac_secret: str = ""
    hmac_header: str = "X-Signature"

    # Timestamp validation (replay attack prevention)
    validate_timestamp: bool = True
    timestamp_tolerance_seconds: int = 300  # 5 minutes

    # IP whitelist
    validate_ip: bool = False
    allowed_ips: list[str] | None = None

    # Trusted proxies for X-Forwarded-For header
    # Only trust X-Forwarded-For if the direct connection comes from these IPs
    # Common values: ["127.0.0.1", "::1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    trusted_proxies: list[str] | None = None


class WebhookSecurityError(Exception):
    """Webhook security validation error."""

    pass


class TwilioSignatureValidator:
    """Validate Twilio webhook signatures.

    Twilio signs all webhook requests with HMAC-SHA1.
    See: https://www.twilio.com/docs/usage/security

    Signature calculation:
    1. Take the full URL of the request
    2. If POST, sort parameters alphabetically and append to URL
    3. Compute HMAC-SHA1 of the result using Auth Token as key
    4. Base64 encode the result
    """

    def __init__(self, auth_token: str) -> None:
        """Initialize validator.

        Args:
            auth_token: Twilio Auth Token
        """
        self.auth_token = auth_token

    def validate(
        self,
        signature: str,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> bool:
        """Validate Twilio signature.

        Args:
            signature: Value from X-Twilio-Signature header
            url: Full request URL (including https://)
            params: POST parameters (if any)

        Returns:
            True if signature is valid
        """
        if not self.auth_token:
            log.warning("Twilio auth token not configured")
            return False

        # Build the data to sign
        data = url
        if params:
            # Sort parameters and append to URL
            sorted_params = sorted(params.items())
            for key, value in sorted_params:
                data += str(key) + str(value)

        # Compute HMAC-SHA1
        expected = base64.b64encode(
            hmac.new(
                self.auth_token.encode("utf-8"),
                data.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")

        # Constant-time comparison
        return hmac.compare_digest(expected, signature)

    async def validate_request(self, request: "Request") -> bool:
        """Validate FastAPI request.

        Args:
            request: FastAPI request

        Returns:
            True if valid
        """
        signature = request.headers.get("X-Twilio-Signature", "")

        # Get full URL
        url = str(request.url)

        # Get form data for POST
        params = {}
        if request.method == "POST":
            try:
                form = await request.form()
                params = dict(form)
            except Exception:
                pass

        return self.validate(signature, url, params)


class SipgateSignatureValidator:
    """Validate sipgate webhook signatures.

    sipgate uses HMAC-SHA256 for webhook signatures.
    """

    def __init__(self, api_token: str) -> None:
        """Initialize validator.

        Args:
            api_token: sipgate API token
        """
        self.api_token = api_token

    def validate(
        self,
        signature: str,
        timestamp: str,
        body: bytes,
    ) -> bool:
        """Validate sipgate signature.

        Args:
            signature: Value from X-Sipgate-Signature header
            timestamp: Value from X-Sipgate-Timestamp header
            body: Raw request body

        Returns:
            True if signature is valid
        """
        if not self.api_token:
            log.warning("sipgate API token not configured")
            return False

        # Construct signing string
        signing_string = f"{timestamp}.{body.decode('utf-8')}"

        # Compute HMAC-SHA256
        expected = hmac.new(
            self.api_token.encode("utf-8"),
            signing_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison
        return hmac.compare_digest(expected, signature)

    async def validate_request(self, request: "Request") -> bool:
        """Validate FastAPI request.

        Args:
            request: FastAPI request

        Returns:
            True if valid
        """
        signature = request.headers.get("X-Sipgate-Signature", "")
        timestamp = request.headers.get("X-Sipgate-Timestamp", "")

        body = await request.body()

        return self.validate(signature, timestamp, body)


class GenericHMACValidator:
    """Generic HMAC signature validator.

    Supports SHA256 and SHA512 signatures for custom integrations.
    """

    def __init__(
        self,
        secret: str,
        algorithm: str = "sha256",
        signature_header: str = "X-Signature",
        timestamp_header: str = "X-Timestamp",
    ) -> None:
        """Initialize validator.

        Args:
            secret: HMAC secret key
            algorithm: Hash algorithm (sha256, sha512)
            signature_header: Header containing signature
            timestamp_header: Header containing timestamp
        """
        self.secret = secret
        self.algorithm = algorithm
        self.signature_header = signature_header
        self.timestamp_header = timestamp_header

        # Get hash function
        if algorithm == "sha256":
            self._hash_func = hashlib.sha256
        elif algorithm == "sha512":
            self._hash_func = hashlib.sha512
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

    def validate(
        self,
        signature: str,
        body: bytes,
        timestamp: str | None = None,
    ) -> bool:
        """Validate signature.

        Args:
            signature: Signature value
            body: Request body
            timestamp: Optional timestamp

        Returns:
            True if valid
        """
        if not self.secret:
            log.warning("HMAC secret not configured")
            return False

        # Build signing data
        if timestamp:
            data = f"{timestamp}.{body.decode('utf-8')}"
        else:
            data = body.decode("utf-8")

        # Compute HMAC
        expected = hmac.new(
            self.secret.encode("utf-8"),
            data.encode("utf-8"),
            self._hash_func,
        ).hexdigest()

        # Handle 'sha256=' prefix
        if signature.startswith("sha256="):
            signature = signature[7:]
        elif signature.startswith("sha512="):
            signature = signature[7:]

        return hmac.compare_digest(expected, signature)

    async def validate_request(self, request: "Request") -> bool:
        """Validate FastAPI request.

        Args:
            request: FastAPI request

        Returns:
            True if valid
        """
        signature = request.headers.get(self.signature_header, "")
        timestamp = request.headers.get(self.timestamp_header)
        body = await request.body()

        return self.validate(signature, body, timestamp)


class TimestampValidator:
    """Validate request timestamps to prevent replay attacks."""

    def __init__(self, tolerance_seconds: int = 300) -> None:
        """Initialize validator.

        Args:
            tolerance_seconds: Maximum age of valid request
        """
        self.tolerance_seconds = tolerance_seconds

    def validate(self, timestamp: str | int | float) -> bool:
        """Validate timestamp is within tolerance.

        Args:
            timestamp: Unix timestamp (seconds)

        Returns:
            True if timestamp is valid
        """
        try:
            ts = float(timestamp)
        except (ValueError, TypeError):
            return False

        now = time.time()
        age = abs(now - ts)

        if age > self.tolerance_seconds:
            log.warning(f"Request timestamp too old: {age:.0f}s")
            return False

        return True


class IPValidator:
    """Validate request source IP addresses."""

    # Known Twilio IP ranges (update periodically)
    TWILIO_IPS = [
        "3.80.0.0/12",
        "54.244.51.0/24",
        "54.172.60.0/24",
        "34.203.250.0/24",
    ]

    # sipgate IPs (example - verify with sipgate)
    SIPGATE_IPS = [
        "217.10.64.0/20",
    ]

    def __init__(self, allowed_ips: list[str] | None = None) -> None:
        """Initialize validator.

        Args:
            allowed_ips: List of allowed IPs/CIDR ranges
        """
        self.allowed_ips = allowed_ips or []

    def validate(self, ip: str) -> bool:
        """Validate source IP.

        Args:
            ip: Source IP address

        Returns:
            True if IP is allowed
        """
        import ipaddress

        try:
            client_ip = ipaddress.ip_address(ip)
        except ValueError:
            return False

        for allowed in self.allowed_ips:
            try:
                if "/" in allowed:
                    # CIDR range
                    network = ipaddress.ip_network(allowed, strict=False)
                    if client_ip in network:
                        return True
                else:
                    # Single IP
                    if client_ip == ipaddress.ip_address(allowed):
                        return True
            except ValueError:
                continue

        return False


class WebhookSecurityManager:
    """Unified webhook security manager.

    Combines signature validation, timestamp checking, and IP validation
    for comprehensive webhook security.

    Usage:
        security = WebhookSecurityManager(config)

        @app.post("/webhook/twilio")
        async def twilio_webhook(request: Request):
            await security.validate_twilio(request)
            # Process webhook...
    """

    def __init__(self, config: WebhookSecurityConfig) -> None:
        """Initialize security manager.

        Args:
            config: Security configuration
        """
        self.config = config

        # Initialize validators
        self._twilio = TwilioSignatureValidator(config.twilio_auth_token)
        self._sipgate = SipgateSignatureValidator(config.sipgate_api_token)
        self._hmac = GenericHMACValidator(config.hmac_secret)
        self._timestamp = TimestampValidator(config.timestamp_tolerance_seconds)
        self._ip = IPValidator(config.allowed_ips)

    async def validate_twilio(self, request: "Request") -> None:
        """Validate Twilio webhook request.

        Args:
            request: FastAPI request

        Raises:
            WebhookSecurityError: If validation fails
        """
        if not self.config.validate_signatures:
            return

        # Validate signature
        if not await self._twilio.validate_request(request):
            log.warning("Invalid Twilio signature", path=str(request.url.path))
            raise WebhookSecurityError("Invalid Twilio signature")

        # Validate IP if enabled (use local validator to avoid race conditions)
        if self.config.validate_ip:
            client_ip = self._get_client_ip(request)
            if not _is_ip_in_network(client_ip, IPValidator.TWILIO_IPS):
                log.warning("Invalid Twilio IP", ip=client_ip)
                raise WebhookSecurityError("Invalid source IP")

        log.debug("Twilio webhook validated", path=str(request.url.path))

    async def validate_sipgate(self, request: "Request") -> None:
        """Validate sipgate webhook request.

        Args:
            request: FastAPI request

        Raises:
            WebhookSecurityError: If validation fails
        """
        if not self.config.validate_signatures:
            return

        # Validate signature
        if not await self._sipgate.validate_request(request):
            log.warning("Invalid sipgate signature", path=str(request.url.path))
            raise WebhookSecurityError("Invalid sipgate signature")

        # Validate timestamp
        if self.config.validate_timestamp:
            timestamp = request.headers.get("X-Sipgate-Timestamp", "")
            if not self._timestamp.validate(timestamp):
                raise WebhookSecurityError("Request timestamp expired")

        # Validate IP if enabled (use local validator to avoid race conditions)
        if self.config.validate_ip:
            client_ip = self._get_client_ip(request)
            if not _is_ip_in_network(client_ip, IPValidator.SIPGATE_IPS):
                log.warning("Invalid sipgate IP", ip=client_ip)
                raise WebhookSecurityError("Invalid source IP")

        log.debug("sipgate webhook validated", path=str(request.url.path))

    async def validate_generic(self, request: "Request") -> None:
        """Validate generic webhook with HMAC signature.

        Args:
            request: FastAPI request

        Raises:
            WebhookSecurityError: If validation fails
        """
        if not self.config.validate_signatures:
            return

        if not await self._hmac.validate_request(request):
            log.warning("Invalid webhook signature", path=str(request.url.path))
            raise WebhookSecurityError("Invalid signature")

    def _get_client_ip(self, request: "Request") -> str:
        """Extract client IP from request.

        Handles X-Forwarded-For header for proxied requests, but only
        trusts it if the direct connection comes from a trusted proxy.

        Security: X-Forwarded-For is client-controlled and can be spoofed.
        We only trust it if the immediate connection is from a known proxy.

        Args:
            request: FastAPI request

        Returns:
            Client IP address
        """
        # Get direct connection IP
        client = request.client
        direct_ip = client.host if client else "unknown"

        # Check X-Forwarded-For only if we have trusted proxies configured
        # AND the direct connection is from a trusted proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded and self.config.trusted_proxies:
            if _is_ip_in_network(direct_ip, self.config.trusted_proxies):
                # Direct connection is from trusted proxy, use X-Forwarded-For
                client_ip = forwarded.split(",")[0].strip()
                log.debug(
                    "Using X-Forwarded-For IP",
                    forwarded_ip=client_ip,
                    proxy_ip=direct_ip,
                )
                return client_ip
            else:
                # Direct connection is NOT from trusted proxy - potential spoofing
                log.warning(
                    "X-Forwarded-For header from untrusted source ignored",
                    direct_ip=direct_ip,
                    forwarded_header=forwarded,
                )

        return direct_ip


def require_twilio_signature(security: WebhookSecurityManager):
    """Decorator to require Twilio signature validation.

    Usage:
        @app.post("/webhook/twilio")
        @require_twilio_signature(security)
        async def twilio_webhook(request: Request):
            # Signature already validated
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: "Request", *args: Any, **kwargs: Any) -> Any:
            await security.validate_twilio(request)
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_sipgate_signature(security: WebhookSecurityManager):
    """Decorator to require sipgate signature validation.

    Usage:
        @app.post("/webhook/sipgate")
        @require_sipgate_signature(security)
        async def sipgate_webhook(request: Request):
            # Signature already validated
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: "Request", *args: Any, **kwargs: Any) -> Any:
            await security.validate_sipgate(request)
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
