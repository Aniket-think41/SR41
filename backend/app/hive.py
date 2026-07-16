"""Hive (crispr) directory ingestion — server-side.

Hive is Think41's multi-tenant HR/ERP ("Keka-like"), deployed at hive.think41.com.
Where app/github.py pulls *content* from repos, this module pulls *people and
structure* from a Hive tenant: employees, delivery projects, allocations
(person↔project), and groups (teams). See HIVE_INTEGRATION.md for the full map.

Two halves, mirroring github.py:

  * OAuth — Hive's only machine-usable token flow is its MCP endpoint's OAuth 2.0
    authorization-code grant with Dynamic Client Registration (server/app/
    entrypoints/mcp/auth.py). SkillShare self-registers a client, drives the
    popup, and exchanges the code for an access token (+ refresh token once Hive
    finishes issuing them — the "A+" path). The token is valid only against
    Hive's MCP tools, so all reads go through the MCP transport below — NOT the
    REST API (that wants RS256/JWKS tokens we can't mint).

  * Transport + client — the MCP JSON-RPC calls are behind an injectable
    ``Transport`` protocol so fetch/normalization is unit-testable with an
    in-memory fake and **no network** (the dashboard mock and tests use fakes).
    ``HiveClient`` turns the raw tool results into normalized dataclasses.

Self-contained: does not import the CLI/MCP integration packages.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from .errors import validation

_TIMEOUT = 20.0
_UA = "skillshare-registry"

# Hive mounts its MCP server (and OAuth routes) under /mcp. RFC 8414 discovery is
# served per-resource at /.well-known/oauth-authorization-server/mcp (JSON); the
# endpoints themselves live under /mcp/*. We prefer the discovery document and
# fall back to these known paths. (Hitting /register at the host root returns the
# SPA's 405 — the earlier bug.)
_DEFAULT_AUTHZ_METADATA = "/.well-known/oauth-authorization-server/mcp"
_DEFAULT_REGISTER = "/mcp/register"
_DEFAULT_AUTHORIZE = "/mcp/authorize"
_DEFAULT_TOKEN = "/mcp/token"
# OAuth scopes to request (identity only — enough to resolve the Hive user; the
# MCP tools are authorized by that user's role, not by these scopes).
_SCOPES = "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile"


def _base_url() -> str:
    from .config import get_settings

    return (get_settings().hive_base_url or "https://hive.think41.com").rstrip("/")


def _resource() -> str:
    """The protected-resource audience Hive expects on authorize/token (RFC 8707);
    Hive rejects a mismatch with invalid_target."""
    return _base_url() + "/mcp/"


def _headers(token: str | None = None) -> dict:
    h = {"User-Agent": _UA, "Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _httpx():
    import httpx  # already a backend dependency

    return httpx


# --------------------------------------------------------------------------- #
# OAuth (MCP authorization-code + Dynamic Client Registration)
# --------------------------------------------------------------------------- #

def pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def discover_endpoints() -> dict:
    """Resolve Hive's OAuth authorize/token/register endpoints, preferring the
    RFC-8414 discovery document and falling back to the FastMCP defaults so a
    connect never hard-fails just because discovery is unreachable."""
    base = _base_url()
    endpoints = {
        "authorization_endpoint": base + _DEFAULT_AUTHORIZE,
        "token_endpoint": base + _DEFAULT_TOKEN,
        "registration_endpoint": base + _DEFAULT_REGISTER,
    }
    httpx = _httpx()
    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_headers(), follow_redirects=True) as c:
            r = c.get(base + _DEFAULT_AUTHZ_METADATA, headers={"Accept": "application/json"})
            # The host's SPA answers unknown paths with 200 text/html — only
            # trust a real JSON metadata document.
            if r.status_code < 400 and "application/json" in r.headers.get("content-type", ""):
                doc = r.json()
                for k in list(endpoints):
                    if doc.get(k):
                        endpoints[k] = doc[k]
    except Exception:
        pass  # fall back to defaults
    return endpoints


def register_client(redirect_uri: str) -> dict:
    """Dynamic Client Registration → returns {client_id, client_secret?}.

    If HIVE_OAUTH_CLIENT_ID is pinned in config we skip DCR and use it."""
    from .config import get_settings

    s = get_settings()
    if s.hive_oauth_client_id:
        return {"client_id": s.hive_oauth_client_id, "client_secret": s.hive_oauth_client_secret or None}

    reg = discover_endpoints()["registration_endpoint"]
    httpx = _httpx()
    body = {
        "client_name": "SkillShare",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none",
    }
    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_headers(), follow_redirects=True) as c:
            r = c.post(reg, json=body)
    except Exception as e:  # pragma: no cover - network
        raise validation(f"Could not reach Hive to register the integration: {e}")
    if r.status_code >= 400:
        raise validation(f"Hive rejected the app registration ({r.status_code}). {r.text[:200]}")
    data = r.json()
    cid = data.get("client_id")
    if not cid:
        raise validation("Hive registration did not return a client_id")
    return {"client_id": cid, "client_secret": data.get("client_secret")}


def authorize_url(client_id: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": _SCOPES,
        "resource": _resource(),
    }
    return discover_endpoints()["authorization_endpoint"] + "?" + urlencode(params)


def _token_request(form: dict) -> dict:
    token_url = discover_endpoints()["token_endpoint"]
    httpx = _httpx()
    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_headers(), follow_redirects=True) as c:
            r = c.post(token_url, data=form)
    except Exception as e:  # pragma: no cover - network
        raise validation(f"Could not reach Hive to exchange the token: {e}")
    if r.status_code >= 400:
        raise validation(f"Hive token exchange failed ({r.status_code}). {r.text[:200]}")
    return r.json()


def exchange_code(
    code: str, redirect_uri: str, code_verifier: str, client_id: str, client_secret: str | None = None
) -> dict:
    """Authorization code → token set. Returns the stored credential blob:
    {access_token, refresh_token?, expires_at?, client_id, client_secret?}."""
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "client_id": client_id,
        "resource": _resource(),
    }
    if client_secret:
        form["client_secret"] = client_secret
    data = _token_request(form)
    return _creds_from_token_response(data, client_id, client_secret)


def refresh_access_token(creds: dict) -> dict:
    """Swap the stored refresh_token for a new access token (A+). Raises if no
    refresh_token is stored (Hive hasn't issued one yet → caller must re-auth)."""
    rt = creds.get("refresh_token")
    if not rt:
        raise validation("This Hive connection has no refresh token — reconnect it")
    form = {
        "grant_type": "refresh_token",
        "refresh_token": rt,
        "client_id": creds.get("client_id", ""),
        "resource": _resource(),
    }
    if creds.get("client_secret"):
        form["client_secret"] = creds["client_secret"]
    data = _token_request(form)
    merged = _creds_from_token_response(data, creds.get("client_id", ""), creds.get("client_secret"))
    # Some servers omit a fresh refresh_token on refresh → keep the old one.
    if not merged.get("refresh_token"):
        merged["refresh_token"] = rt
    return merged


def _creds_from_token_response(data: dict, client_id: str, client_secret: str | None) -> dict:
    access = data.get("access_token")
    if not access:
        raise validation("Hive did not return an access token")
    creds = {
        "access_token": access,
        "refresh_token": data.get("refresh_token"),
        "client_id": client_id,
        "client_secret": client_secret,
    }
    expires_in = data.get("expires_in")
    if isinstance(expires_in, (int, float)):
        creds["expires_at"] = int(time.time()) + int(expires_in)
    return creds


def token_expired(creds: dict, *, skew: int = 120) -> bool:
    exp = creds.get("expires_at")
    if not isinstance(exp, (int, float)):
        return False  # unknown TTL → assume valid; a 401 will force a refresh
    return time.time() >= (exp - skew)


# --------------------------------------------------------------------------- #
# MCP transport (JSON-RPC over Streamable HTTP) — injectable for tests
# --------------------------------------------------------------------------- #

class Transport(Protocol):
    def call_tool(self, tool: str, arguments: dict) -> Any: ...


class McpHttpTransport:
    """Calls Hive MCP tools at ``{hive_base_url}/mcp/?tenant=<code>`` with the
    OAuth access token. Implements the minimal Streamable-HTTP handshake
    (initialize → notifications/initialized → tools/call), reusing the session
    id across calls. Kept behind the Transport protocol so tests/mocks bypass it.
    """

    def __init__(self, access_token: str, tenant: str):
        self.access_token = access_token
        self.tenant = tenant
        self._session_id: str | None = None
        self._rpc_id = 0

    def _url(self) -> str:
        return f"{_base_url()}/mcp/?tenant={self.tenant}"

    def _post(self, client, payload: dict):
        headers = _headers(self.access_token)
        # Streamable HTTP requires accepting both JSON and the SSE stream.
        headers["Accept"] = "application/json, text/event-stream"
        headers["Content-Type"] = "application/json"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        r = client.post(self._url(), json=payload, headers=headers)
        sid = r.headers.get("mcp-session-id") or r.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid
        return r

    def _next_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    @staticmethod
    def _parse(r) -> dict:
        """Parse a JSON or SSE (text/event-stream) JSON-RPC response body."""
        ctype = r.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            for line in r.text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    chunk = line[len("data:"):].strip()
                    if chunk:
                        try:
                            return json.loads(chunk)
                        except Exception:
                            continue
            return {}
        try:
            return r.json()
        except Exception:
            return {}

    def _initialize(self, client) -> None:
        if self._session_id:
            return
        init = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "skillshare", "version": "1.0"},
            },
        }
        r = self._post(client, init)
        if r.status_code == 401:
            raise validation("hive_unauthorized")
        if r.status_code >= 400:
            raise validation(f"Hive MCP initialize failed ({r.status_code})")
        # Notify initialized (best-effort; some servers require it before tools).
        self._post(client, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call_tool(self, tool: str, arguments: dict) -> Any:
        httpx = _httpx()
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            self._initialize(client)
            payload = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
            r = self._post(client, payload)
            if r.status_code == 401:
                raise validation("hive_unauthorized")
            if r.status_code >= 400:
                raise validation(f"Hive tool '{tool}' failed ({r.status_code}). {r.text[:200]}")
            return _extract_tool_result(self._parse(r), tool)


def _extract_tool_result(body: dict, tool: str) -> Any:
    """Pull the structured payload out of a JSON-RPC tools/call response.

    MCP returns either ``result.structuredContent`` or ``result.content[]`` with
    a JSON string in ``.text``. We prefer structured, then parse text."""
    if body.get("error"):
        err = body["error"]
        raise validation(f"Hive tool '{tool}' error: {err.get('message', err)}")
    result = body.get("result", body)
    if isinstance(result, dict):
        if "structuredContent" in result and result["structuredContent"] is not None:
            sc = result["structuredContent"]
            # FastMCP wraps a bare list as {"result": [...]}
            if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
                return sc["result"]
            return sc
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                    try:
                        return json.loads(item["text"])
                    except Exception:
                        return item["text"]
    return result


# --------------------------------------------------------------------------- #
# Normalized records
# --------------------------------------------------------------------------- #

@dataclass
class HiveMember:
    external_ref: str            # stable person key (member_id, else employee id)
    email: str | None
    display_name: str
    is_active: bool
    status: str = ""
    department: str = ""
    designation: str = ""
    manager_ref: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class HiveProject:
    external_ref: str            # Hive project id
    name: str
    code: str = ""
    status: str = ""
    account_name: str = ""
    tech_stack: list = field(default_factory=list)
    pm_name: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class HiveGroup:
    external_ref: str            # Hive group id
    name: str
    description: str = ""
    is_active: bool = True
    member_refs: list = field(default_factory=list)  # employee ids
    raw: dict = field(default_factory=dict)


@dataclass
class HiveAllocation:
    employee_ref: str
    project_ref: str
    percentage: int = 0
    is_active: bool = True
    status: str = ""
    role: str = ""
    raw: dict = field(default_factory=dict)


def _as_list(result: Any) -> list[dict]:
    """Normalize a tool result to a list of dicts (handles {items:[...]} etc.)."""
    if result is None:
        return []
    if isinstance(result, dict):
        for key in ("items", "employees", "projects", "groups", "allocations", "members", "result"):
            if isinstance(result.get(key), list):
                return result[key]
        return [result]
    if isinstance(result, list):
        return [x for x in result if isinstance(x, dict)]
    return []


def _first(d: dict, *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return default


# --------------------------------------------------------------------------- #
# High-level client
# --------------------------------------------------------------------------- #

class HiveClient:
    """Reads a Hive tenant through MCP tools and yields normalized records.

    Pagination: employees/groups use cursor tools; projects/allocations return
    all rows in one call (per HIVE_INTEGRATION.md §1)."""

    def __init__(self, transport: Transport, tenant: str):
        self.t = transport
        self.tenant = tenant

    def _paginate(self, tool: str, base_args: dict, limit: int = 200) -> list[dict]:
        out: list[dict] = []
        cursor = None
        for _ in range(200):  # hard stop against a bad cursor loop
            args = dict(base_args)
            args["limit"] = limit
            if cursor:
                args["cursor"] = cursor
            res = self.t.call_tool(tool, args)
            rows = _as_list(res)
            out.extend(rows)
            cursor = res.get("next_cursor") if isinstance(res, dict) else None
            if not cursor or not rows:
                break
        return out

    def list_members(self) -> list[HiveMember]:
        rows = self._paginate("list_employees", {})
        out = []
        for r in rows:
            out.append(
                HiveMember(
                    external_ref=str(_first(r, "member_id", "id", "code", default="")),
                    email=_first(r, "workspace_email", "email"),
                    display_name=_first(r, "display_name", "name", default="") or "",
                    is_active=bool(r.get("is_active", True)),
                    status=_first(r, "status", default="") or "",
                    department=_first(r, "department", default="") or "",
                    designation=_first(r, "designation", default="") or "",
                    manager_ref=_first(r, "manager_employee_id", "manager_ref"),
                    raw=r,
                )
            )
        return [m for m in out if m.external_ref]

    def list_projects(self) -> list[HiveProject]:
        rows = _as_list(self.t.call_tool("list_projects", {}))
        out = []
        for r in rows:
            out.append(
                HiveProject(
                    external_ref=str(_first(r, "id", "code", default="")),
                    name=_first(r, "name", default="") or "",
                    code=_first(r, "code", default="") or "",
                    status=_first(r, "status", default="") or "",
                    account_name=_first(r, "account_name", default="") or "",
                    tech_stack=r.get("tech_stack") or [],
                    pm_name=_first(r, "pm_display_name", default="") or "",
                    raw=r,
                )
            )
        return [p for p in out if p.external_ref]

    def list_allocations(self) -> list[HiveAllocation]:
        rows = _as_list(self.t.call_tool("list_allocations", {}))
        out = []
        for r in rows:
            emp = _first(r, "employee_id", "employee_ref")
            proj = _first(r, "project_id", "project_ref")
            if not emp or not proj:
                continue
            out.append(
                HiveAllocation(
                    employee_ref=str(emp),
                    project_ref=str(proj),
                    percentage=int(r.get("percentage") or 0),
                    is_active=bool(r.get("is_active", True)),
                    status=_first(r, "status", default="") or "",
                    role=_first(r, "role", "allocation_type", default="") or "",
                    raw=r,
                )
            )
        return out

    def list_groups(self, *, with_members: bool = True) -> list[HiveGroup]:
        rows = self._paginate("list_groups", {})
        out = []
        for r in rows:
            gref = str(_first(r, "id", default=""))
            if not gref:
                continue
            member_refs: list[str] = []
            if with_members:
                try:
                    mres = self._paginate("list_group_members", {"group_id": gref}, limit=500)
                    member_refs = [
                        str(_first(m, "employee_id", "id"))
                        for m in mres
                        if _first(m, "employee_id", "id")
                    ]
                except Exception:
                    member_refs = []
            out.append(
                HiveGroup(
                    external_ref=gref,
                    name=_first(r, "name", default="") or "",
                    description=_first(r, "description", default="") or "",
                    is_active=bool(r.get("is_active", True)),
                    member_refs=member_refs,
                    raw=r,
                )
            )
        return out


def build_client(creds: dict, tenant: str) -> HiveClient:
    """Construct a live HiveClient from a stored credential blob."""
    token = creds.get("access_token")
    if not token:
        raise validation("This Hive connection has no access token — reconnect it")
    return HiveClient(McpHttpTransport(token, tenant), tenant)


def validate_connection(creds: dict, tenant: str) -> dict:
    """Confirm the token works by making one cheap read, and return account
    metadata for the connection row. Raises on a bad/expired token."""
    client = build_client(creds, tenant)
    # A tiny employees read is the cheapest liveness probe.
    client.t.call_tool("list_employees", {"limit": 1})
    return {
        "account_label": tenant,
        "account_type": "Tenant",
        "account_url": f"{_base_url()}/",
    }
