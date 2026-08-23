"""Authentication and Authorization for Alcyoneus OS.

Supports OAuth2/OIDC, JWT validation, mTLS, token introspection, scopes/permissions.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import aiohttp
import jwt
from cryptography.hazmat.primitives import serialization
from jwt.exceptions import InvalidTokenError


logger = logging.getLogger("alcyoneus.auth")


class AuthError(Exception):
    """Base authentication/authorization error."""


class TokenExpiredError(AuthError):
    pass


class TokenInvalidError(AuthError):
    pass


class InsufficientScopeError(AuthError):
    pass


class MTLSError(AuthError):
    pass


@dataclass
class TokenClaims:
    """Parsed JWT claims."""

    sub: str
    iss: str
    aud: str | list[str]
    exp: int
    iat: int
    scopes: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    tenant_id: str | None = None
    roles: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        return time.time() > self.exp

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions

    def has_role(self, role: str) -> bool:
        return role in self.roles


@dataclass
class OAuth2Config:
    """OAuth2/OIDC configuration."""

    issuer_url: str
    client_id: str
    client_secret: str | None = None
    scopes: list[str] = field(default_factory=lambda: ["openid", "profile", "email"])
    redirect_uri: str | None = None
    jwks_uri: str | None = None
    token_endpoint: str | None = None
    introspection_endpoint: str | None = None
    revocation_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    use_pkce: bool = True
    pkce_code_challenge_method: str = "S256"


class JWKSCache:
    """Cache for JSON Web Key Sets."""

    def __init__(self, ttl: int = 3600):
        self._cache: dict[str, tuple[dict, float]] = {}
        self._ttl = ttl
        self._lock = asyncio.Lock()

    async def get_keys(self, jwks_uri: str) -> dict:
        async with self._lock:
            now = time.time()
            if jwks_uri in self._cache:
                keys, cached_at = self._cache[jwks_uri]
                if now - cached_at < self._ttl:
                    return keys

            async with aiohttp.ClientSession() as session:
                async with session.get(jwks_uri) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    self._cache[jwks_uri] = (data, now)
                    return data

    def clear(self):
        self._cache.clear()


_jwks_cache = JWKSCache()


class JWTValidator:
    """JWT token validation with JWKS support."""

    def __init__(
        self,
        issuer: str,
        audience: str | list[str],
        jwks_uri: str | None = None,
        public_key: str | None = None,
        algorithms: list[str] = field(default_factory=lambda: ["RS256"]),
        leeway: int = 30,
    ):
        self.issuer = issuer
        self.audience = audience if isinstance(audience, list) else [audience]
        self.jwks_uri = jwks_uri
        self.public_key = public_key
        self.algorithms = algorithms
        self.leeway = leeway
        self._key_cache: dict[str, Any] = {}

    async def validate(self, token: str) -> TokenClaims:
        """Validate JWT and return claims."""
        try:
            # Get signing key
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            key = await self._get_signing_key(kid)

            # Decode and verify
            claims = jwt.decode(
                token,
                key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway,
                options={"verify_aud": True, "verify_iss": True, "verify_exp": True},
            )

            return TokenClaims(
                sub=claims.get("sub", ""),
                iss=claims.get("iss", ""),
                aud=claims.get("aud", ""),
                exp=claims.get("exp", 0),
                iat=claims.get("iat", 0),
                scopes=claims.get("scopes", claims.get("scope", "").split()),
                permissions=claims.get("permissions", []),
                tenant_id=claims.get("tenant_id"),
                roles=claims.get("roles", claims.get("realm_access", {}).get("roles", [])),
                raw=claims,
            )
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidAudienceError:
            raise TokenInvalidError("Invalid audience")
        except jwt.InvalidIssuerError:
            raise TokenInvalidError("Invalid issuer")
        except InvalidTokenError as e:
            raise TokenInvalidError(f"Invalid token: {e}")

    async def _get_signing_key(self, kid: str | None) -> Any:
        if kid and kid in self._key_cache:
            return self._key_cache[kid]

        if self.public_key:
            key = serialization.load_pem_public_key(self.public_key.encode())
            if kid:
                self._key_cache[kid] = key
            return key

        if not self.jwks_uri:
            raise TokenInvalidError("No JWKS URI or public key configured")

        jwks = await _jwks_cache.get_keys(self.jwks_uri)
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid or not kid:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
                if kid:
                    self._key_cache[kid] = key
                return key

        raise TokenInvalidError(f"Signing key not found for kid: {kid}")


class TokenIntrospector:
    """OAuth2 token introspection (RFC 7662)."""

    def __init__(
        self,
        introspection_endpoint: str,
        client_id: str,
        client_secret: str,
        timeout: float = 10.0,
    ):
        self.introspection_endpoint = introspection_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._cache: dict[str, tuple[dict, float]] = {}
        self._cache_ttl = 300  # 5 minutes

    async def introspect(self, token: str, token_type_hint: str = "access_token") -> dict:  # noqa: S107
        """Introspect token, returns active status and claims."""
        # Check cache
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        now = time.time()
        if token_hash in self._cache:
            cached, cached_at = self._cache[token_hash]
            if now - cached_at < self._cache_ttl:
                return cached

        auth = aiohttp.BasicAuth(self.client_id, self.client_secret)
        data = {"token": token, "token_type_hint": token_type_hint}

        async with (
            aiohttp.ClientSession() as session,
            session.post(
                self.introspection_endpoint,
                data=data,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp,
        ):
            resp.raise_for_status()
            result = await resp.json()

        self._cache[token_hash] = (result, now)
        return result

    async def is_active(self, token: str) -> bool:
        result = await self.introspect(token)
        return result.get("active", False)


class MTLSValidator:
    """Mutual TLS certificate validation."""

    def __init__(
        self,
        ca_cert_path: str | None = None,
        ca_cert_pem: str | None = None,
        verify_hostname: bool = True,
        allowed_ous: list[str] | None = None,
        allowed_cns: list[str] | None = None,
    ):
        self.verify_hostname = verify_hostname
        self.allowed_ous = allowed_ous or []
        self.allowed_cns = allowed_cns or []
        self._ca_cert = None

        if ca_cert_path:
            with open(ca_cert_path, "rb") as f:
                self._ca_cert = f.read()
        elif ca_cert_pem:
            self._ca_cert = ca_cert_pem.encode()

    def validate_certificate(self, cert_pem: str) -> dict:
        """Validate client certificate, return parsed info."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes

        cert = x509.load_pem_x509_certificate(cert_pem.encode())

        # Verify against CA if provided
        if self._ca_cert:
            ca_cert = x509.load_pem_x509_certificate(self._ca_cert)
            ca_public_key = ca_cert.public_key()
            try:
                ca_public_key.verify(
                    cert.signature,
                    cert.tbs_certificate_bytes,
                    cert.signature_algorithm_parameters,
                    cert.signature_hash_algorithm,
                )
            except Exception as e:
                raise MTLSError(f"Certificate chain validation failed: {e}")

        # Check expiration
        now = datetime.now(UTC)
        if cert.not_valid_after_utc < now:
            raise MTLSError("Certificate has expired")
        if cert.not_valid_before_utc > now:
            raise MTLSError("Certificate not yet valid")

        # Extract subject info
        subject = cert.subject
        cn = None
        ous = []
        for attr in subject:
            if attr.oid == x509.NameOID.COMMON_NAME:
                cn = attr.value
            elif attr.oid == x509.NameOID.ORGANIZATIONAL_UNIT_NAME:
                ous.append(attr.value)

        # Check allowed CN/OUs
        if self.allowed_cns and cn not in self.allowed_cns:
            raise MTLSError(f"CN not allowed: {cn}")
        if self.allowed_ous and not any(ou in self.allowed_ous for ou in ous):
            raise MTLSError(f"OU not allowed: {ous}")

        return {
            "subject": subject.rfc4514_string(),
            "cn": cn,
            "ous": ous,
            "serial_number": cert.serial_number,
            "not_before": cert.not_valid_before_utc.isoformat(),
            "not_after": cert.not_valid_after_utc.isoformat(),
            "fingerprint_sha256": cert.fingerprint(hashes.SHA256()).hex(),
        }


class ScopeChecker:
    """Scope and permission checking."""

    def __init__(
        self,
        required_scopes: list[str] | None = None,
        required_permissions: list[str] | None = None,
    ):
        self.required_scopes = set(required_scopes or [])
        self.required_permissions = set(required_permissions or [])

    def check(self, claims: TokenClaims) -> None:
        missing_scopes = self.required_scopes - set(claims.scopes)
        if missing_scopes:
            raise InsufficientScopeError(f"Missing required scopes: {missing_scopes}")

        missing_perms = self.required_permissions - set(claims.permissions)
        if missing_perms:
            raise InsufficientScopeError(f"Missing required permissions: {missing_perms}")


class AuthMiddleware:
    """ASGI middleware for authentication."""

    def __init__(
        self,
        app,
        jwt_validator: JWTValidator | None = None,
        token_introspector: TokenIntrospector | None = None,
        mtls_validator: MTLSValidator | None = None,
        excluded_paths: list[str] = field(default_factory=lambda: ["/health", "/ready"]),
        bearer_header: str = "Authorization",
        mtls_header: str = "X-Client-Cert",
    ):
        self.app = app
        self.jwt_validator = jwt_validator
        self.token_introspector = token_introspector
        self.mtls_validator = mtls_validator
        self.excluded_paths = excluded_paths
        self.bearer_header = bearer_header
        self.mtls_header = mtls_header

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(p) for p in self.excluded_paths):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(self.bearer_header.lower().encode(), b"").decode()

        claims = None
        auth_method = None

        # Try JWT
        if auth_header.startswith("Bearer ") and self.jwt_validator:
            token = auth_header[7:]
            try:
                claims = await self.jwt_validator.validate(token)
                auth_method = "jwt"
            except AuthError as e:
                await self._send_error(send, 401, str(e))
                return

        # Try mTLS
        if not claims and self.mtls_validator:
            cert_header = headers.get(self.mtls_header.lower().encode(), b"").decode()
            if cert_header:
                try:
                    cert_info = self.mtls_validator.validate_certificate(cert_header)
                    # Create minimal claims from cert
                    claims = TokenClaims(
                        sub=cert_info.get("cn", "unknown"),
                        iss="mtls",
                        aud="alcyoneus",
                        exp=int(time.time()) + 3600,
                        iat=int(time.time()),
                        raw=cert_info,
                    )
                    auth_method = "mtls"
                except MTLSError as e:
                    await self._send_error(send, 401, str(e))
                    return

        # Try token introspection
        if not claims and self.token_introspector and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                result = await self.token_introspector.introspect(token)
                if result.get("active"):
                    claims = TokenClaims(
                        sub=result.get("sub", "unknown"),
                        iss=result.get("iss", "introspection"),
                        aud=result.get("aud", "alcyoneus"),
                        exp=result.get("exp", int(time.time()) + 3600),
                        iat=result.get("iat", int(time.time())),
                        scopes=result.get("scope", "").split(),
                        permissions=result.get("permissions", []),
                        tenant_id=result.get("tenant_id"),
                        roles=result.get("roles", []),
                        raw=result,
                    )
                    auth_method = "introspection"
                else:
                    await self._send_error(send, 401, "Token inactive")
                    return
            except Exception as e:
                await self._send_error(send, 401, f"Introspection failed: {e}")
                return

        if not claims:
            await self._send_error(send, 401, "Authentication required")
            return

        # Attach claims to scope for downstream use
        scope["auth"] = {
            "claims": claims,
            "method": auth_method,
            "authenticated": True,
        }

        await self.app(scope, receive, send)

    async def _send_error(self, send, status: int, message: str):
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps({"error": message}).encode(),
            }
        )


def require_scopes(*scopes: str):
    """Decorator to require scopes on a handler."""

    def decorator(func: Callable):
        async def wrapper(request, *args, **kwargs):
            auth = request.scope.get("auth")
            if not auth or not auth.get("authenticated"):
                raise AuthError("Not authenticated")

            claims = auth["claims"]
            missing = set(scopes) - set(claims.scopes)
            if missing:
                raise InsufficientScopeError(f"Missing scopes: {missing}")

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_permissions(*perms: str):
    """Decorator to require permissions on a handler."""

    def decorator(func: Callable):
        async def wrapper(request, *args, **kwargs):
            auth = request.scope.get("auth")
            if not auth or not auth.get("authenticated"):
                raise AuthError("Not authenticated")

            claims = auth["claims"]
            missing = set(perms) - set(claims.permissions)
            if missing:
                raise InsufficientScopeError(f"Missing permissions: {missing}")

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


class APIKeyManager:
    """Simple API key management for service-to-service auth."""

    def __init__(self, key_prefix: str = "alc_"):
        self.key_prefix = key_prefix
        self._keys: dict[str, dict] = {}  # key_hash -> {name, scopes, created, last_used}

    def generate_key(self, name: str, scopes: list[str] | None = None) -> str:
        """Generate a new API key."""
        import secrets

        random_part = secrets.token_urlsafe(32)
        key = f"{self.key_prefix}{random_part}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        self._keys[key_hash] = {
            "name": name,
            "scopes": scopes or [],
            "created": time.time(),
            "last_used": None,
        }
        return key

    def validate_key(self, key: str) -> TokenClaims | None:
        """Validate API key and return claims."""
        if not key.startswith(self.key_prefix):
            return None
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        info = self._keys.get(key_hash)
        if not info:
            return None
        info["last_used"] = time.time()
        return TokenClaims(
            sub=f"apikey:{info['name']}",
            iss="apikey",
            aud="alcyoneus",
            exp=int(time.time()) + 86400 * 365,  # 1 year
            iat=int(time.time()),
            scopes=info["scopes"],
            raw={"type": "api_key", "name": info["name"]},
        )

    def revoke_key(self, key: str) -> bool:
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        if key_hash in self._keys:
            del self._keys[key_hash]
            return True
        return False

    def list_keys(self) -> list[dict]:
        return [
            {
                "name": v["name"],
                "scopes": v["scopes"],
                "created": v["created"],
                "last_used": v["last_used"],
            }
            for v in self._keys.values()
        ]


__all__ = [
    "APIKeyManager",
    "AuthError",
    "AuthMiddleware",
    "InsufficientScopeError",
    "JWKSCache",
    "JWTValidator",
    "MTLSError",
    "MTLSValidator",
    "OAuth2Config",
    "ScopeChecker",
    "TokenClaims",
    "TokenExpiredError",
    "TokenIntrospector",
    "TokenInvalidError",
    "require_permissions",
    "require_scopes",
]
