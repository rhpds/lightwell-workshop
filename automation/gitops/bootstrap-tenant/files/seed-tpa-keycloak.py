#!/usr/bin/env python3
"""
Keycloak + TPA seed for a tenant uploader (ported from deploy-tpa.yml).
Idempotent: trustify-ui client, TPA API scopes, per-tenant uploader user, demo SBOM upload.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

TPA_SCOPE_NAMES = [
    "create.sbom",
    "read.sbom",
    "update.sbom",
    "delete.sbom",
    "create.advisory",
    "create.importer",
    "create.metadata",
    "create.weakness",
    "upload.dataset",
]
SBOM_DEFAULT_SCOPES = ["create.sbom", "read.sbom", "update.sbom", "delete.sbom"]


def env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        print(f"ERROR: missing env {name}", file=sys.stderr)
        sys.exit(1)
    return val or ""


def kc_request(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
    insecure: bool = True,
) -> tuple[int, Any]:
    data = None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    ctx = ssl._create_unverified_context() if insecure else None
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
            raw = resp.read().decode("utf-8") or ""
            return resp.status, json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            parsed = raw
        return e.code, parsed


def admin_token(keycloak_url: str, admin_user: str, admin_pass: str) -> str:
    url = f"{keycloak_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
    body = urllib.parse.urlencode(
        {
            "client_id": "admin-cli",
            "username": admin_user,
            "password": admin_pass,
            "grant_type": "password",
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        return json.loads(resp.read().decode())["access_token"]


def ensure_client_scopes(realm_base: str, token: str) -> dict[str, str]:
    """Create TPA scopes if missing; return name -> id."""
    code, existing = kc_request("GET", f"{realm_base}/client-scopes", token)
    by_name: dict[str, str] = {}
    if code == 200 and isinstance(existing, list):
        for item in existing:
            if item.get("name"):
                by_name[item["name"]] = item["id"]

    for name in TPA_SCOPE_NAMES:
        if name in by_name:
            continue
        code, created = kc_request(
            "POST",
            f"{realm_base}/client-scopes",
            token,
            {
                "name": name,
                "protocol": "openid-connect",
                "attributes": {
                    "include.in.token.scope": "true",
                    "display.on.consent.screen": "false",
                },
            },
        )
        if code in (201, 409):
            if code == 201 and isinstance(created, dict) and created.get("id"):
                by_name[name] = created["id"]
            elif code == 409:
                code2, all_scopes = kc_request("GET", f"{realm_base}/client-scopes", token)
                if code2 == 200 and isinstance(all_scopes, list):
                    for item in all_scopes:
                        if item.get("name") == name:
                            by_name[name] = item["id"]
            print(f"Client scope {name}: HTTP {code}")
        else:
            print(f"WARN: client scope {name}: HTTP {code} {created}", file=sys.stderr)
    return by_name


def configure_trustify_client(
    realm_base: str,
    token: str,
    client_id: str,
    tpa_url: str,
    trustify_url: str,
    scope_ids: dict[str, str],
) -> None:
    code, clients = kc_request(
        "GET",
        f"{realm_base}/clients?clientId={urllib.parse.quote(client_id)}",
        token,
    )
    if code != 200 or not isinstance(clients, list) or not clients:
        print(f"ERROR: trustify client {client_id} not found (HTTP {code})", file=sys.stderr)
        sys.exit(1)
    internal_id = clients[0]["id"]
    code, full = kc_request("GET", f"{realm_base}/clients/{internal_id}", token)
    if code != 200 or not isinstance(full, dict):
        print(f"ERROR: could not load client {client_id}", file=sys.stderr)
        sys.exit(1)

    redirects = set(full.get("redirectUris") or [])
    redirects.add(f"{trustify_url.rstrip('/')}/*")
    redirects.add(f"{tpa_url.rstrip('/')}/*")
    full["redirectUris"] = sorted(redirects)
    full["webOrigins"] = ["*"]
    full["directAccessGrantsEnabled"] = True
    full["publicClient"] = True

    code, resp = kc_request("PUT", f"{realm_base}/clients/{internal_id}", token, full)
    if code == 204:
        print(f"Updated {client_id}: direct access grants + redirect URIs")
    else:
        print(f"WARN: client PUT HTTP {code}: {resp}", file=sys.stderr)

    for scope_name in TPA_SCOPE_NAMES:
        sid = scope_ids.get(scope_name)
        if not sid:
            continue
        code, _ = kc_request(
            "PUT",
            f"{realm_base}/clients/{internal_id}/default-client-scopes/{sid}",
            token,
        )
        if code in (204, 409):
            print(f"Default scope on {client_id}: {scope_name}")
        else:
            print(f"WARN: attach scope {scope_name}: HTTP {code}", file=sys.stderr)


def ensure_uploader_user(
    realm_base: str,
    token: str,
    username: str,
    password: str,
) -> None:
    code, users = kc_request(
        "GET",
        f"{realm_base}/users?username={urllib.parse.quote(username)}",
        token,
    )
    if code != 200:
        print(f"ERROR: list users HTTP {code}", file=sys.stderr)
        sys.exit(1)
    if isinstance(users, list) and users:
        user_id = users[0]["id"]
        print(f"Keycloak user {username} already exists (id={user_id})")
        code, full_user = kc_request("GET", f"{realm_base}/users/{user_id}", token)
        if code == 200 and isinstance(full_user, dict):
            full_user["requiredActions"] = []
            full_user["emailVerified"] = True
            full_user["enabled"] = True
            full_user["email"] = f"{username}@lightwell.example.com"
            full_user["firstName"] = "Lightwell"
            full_user["lastName"] = "Uploader"
            kc_request("PUT", f"{realm_base}/users/{user_id}", token, full_user)
            print(f"Cleared required actions and profile for {username}")
        cred_url = f"{realm_base}/users/{user_id}/reset-password"
        code, resp = kc_request(
            "PUT",
            cred_url,
            token,
            {"type": "password", "value": password, "temporary": False},
        )
        if code == 204:
            print(f"Reset password for {username}")
        else:
            print(f"WARN: password reset HTTP {code}: {resp}", file=sys.stderr)
        return

    body = {
        "username": username,
        "enabled": True,
        "emailVerified": True,
        "email": f"{username}@lightwell.example.com",
        "firstName": "Lightwell",
        "lastName": "Uploader",
        "requiredActions": [],
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }
    code, resp = kc_request("POST", f"{realm_base}/users", token, body)
    if code in (201, 409):
        print(f"Created Keycloak user {username} (HTTP {code})")
    else:
        print(f"ERROR: create user HTTP {code}: {resp}", file=sys.stderr)
        sys.exit(1)


def tpa_password_token(
    keycloak_url: str,
    realm: str,
    client_id: str,
    username: str,
    password: str,
) -> str:
    url = f"{keycloak_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/token"
    body = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": client_id,
            "username": username,
            "password": password,
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            return data.get("access_token") or ""
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"ERROR: TPA OAuth token failed HTTP {e.code}: {err}", file=sys.stderr)
        return ""


def upload_sbom(tpa_url: str, token: str, label: str, path: str) -> None:
    if not os.path.isfile(path):
        print(f"WARN: SBOM file missing: {path}")
        return
    q = urllib.parse.urlencode({"labels.name": label, "format": "cyclonedx"})
    url = f"{tpa_url.rstrip('/')}/api/v2/sbom?{q}"
    with open(path, "rb") as f:
        payload = f.read()
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        },
    )
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
            print(f"TPA SBOM upload OK HTTP {resp.status} label={label}")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"WARN: TPA upload HTTP {e.code}: {err}", file=sys.stderr)


def main() -> None:
    keycloak_url = env("KEYCLOAK_URL", required=True)
    realm = env("KEYCLOAK_TPA_REALM", "trusted-profile-analyzer")
    client_id = env("TPA_OAUTH_CLIENT_ID", "trustify-ui")
    tpa_url = env("TPA_URL", required=True)
    trustify_url = env("TPA_TRUSTIFY_URL", tpa_url)
    uploader = env("TPA_UPLOADER_USERNAME", required=True)
    password = env("TPA_UPLOADER_PASSWORD", required=True)
    sbom_label = env("TPA_SBOM_LABEL", required=True)
    sbom_file = env("TPA_SBOM_FILE", "/seed/demo-sbom.cyclonedx.json")

    kc_admin_user = env("KEYCLOAK_ADMIN_USER", required=True)
    kc_admin_pass = env("KEYCLOAK_ADMIN_PASSWORD", required=True)

    realm_base = f"{keycloak_url.rstrip('/')}/admin/realms/{realm}"
    token = admin_token(keycloak_url, kc_admin_user, kc_admin_pass)
    print("Keycloak admin token obtained")

    scope_ids = ensure_client_scopes(realm_base, token)
    configure_trustify_client(realm_base, token, client_id, tpa_url, trustify_url, scope_ids)

    tenant_user = env("LIGHTWELL_USERNAME", required=True)
    tenant_password = env("LIGHTWELL_PASSWORD", required=True)
    tpa_admin_user = env("TPA_ADMIN_USERNAME", "admin")
    tpa_admin_password = env("TPA_ADMIN_PASSWORD", tenant_password)

    for label, username, user_password in (
        ("uploader", uploader, password),
        ("tenant", tenant_user, tenant_password),
        ("admin", tpa_admin_user, tpa_admin_password),
    ):
        ensure_uploader_user(realm_base, token, username, user_password)
        print(f"Keycloak Trustify user ready ({label}): {username}")

    access = tpa_password_token(keycloak_url, realm, client_id, uploader, password)
    if not access:
        sys.exit(1)
    print("TPA uploader OAuth token obtained")

    upload_sbom(tpa_url, access, sbom_label, sbom_file)
    print("TPA seed complete")


if __name__ == "__main__":
    main()
