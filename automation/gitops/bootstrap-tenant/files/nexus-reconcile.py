#!/usr/bin/env python3
"""
Idempotent Nexus reconcile: Lightwell Maven repos + EDA webhooks (ExtDirect).
Ported from lightwell-demo-collateral/ansible/playbooks/tasks/deploy-nexus-complete.yml
"""
from __future__ import annotations

import json
import os
import ssl
import time
import sys
import urllib.error
import urllib.request
from typing import Any


def env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        print(f"ERROR: missing required env {name}", file=sys.stderr)
        sys.exit(1)
    return val or ""


def request(
    method: str,
    url: str,
    user: str,
    password: str,
    body: dict | None = None,
    insecure: bool = True,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    req.add_header("Authorization", _basic_auth(user, password))
    ctx = ssl._create_unverified_context() if insecure else None
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
            raw = resp.read().decode("utf-8") or "null"
            return resp.status, json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            parsed = raw
        return e.code, parsed


def _basic_auth(user: str, password: str) -> str:
    import base64

    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def wait_for_nexus(base: str, user: str, password: str) -> None:
    url = f"{base.rstrip('/')}/service/rest/v1/status"
    for attempt in range(1, 31):
        code, _ = request("GET", url, user, password)
        if code == 200:
            print("Nexus API is ready")
            return
        print(f"Waiting for Nexus API ({attempt}/30), status={code}")
        time.sleep(5)
    print("ERROR: Nexus API not ready", file=sys.stderr)
    sys.exit(1)


def enable_anonymous(base: str, user: str, password: str) -> None:
    url = f"{base.rstrip('/')}/service/rest/v1/security/anonymous"
    body = {
        "enabled": True,
        "userId": "anonymous",
        "realmName": "NexusAuthorizingRealm",
    }
    code, _ = request("PUT", url, user, password, body)
    if code in (200, 204):
        print("Anonymous access enabled (or already set)")
    else:
        print(f"Note: anonymous access PUT returned {code} (ignored)")


def repo_exists(base: str, user: str, password: str, name: str) -> bool:
    url = f"{base.rstrip('/')}/service/rest/v1/repositories"
    code, data = request("GET", url, user, password)
    if code != 200 or not isinstance(data, list):
        return False
    return any(r.get("name") == name for r in data)


def create_proxy(
    base: str,
    user: str,
    password: str,
    item: dict,
    lw_user: str,
    lw_pass: str,
) -> None:
    name = item["name"]
    if repo_exists(base, user, password, name):
        print(f"Skip proxy repo (exists): {name}")
        return
    body: dict[str, Any] = {
        "name": name,
        "online": True,
        "storage": {
            "blobStoreName": "default",
            "strictContentTypeValidation": True,
        },
        "proxy": {
            "remoteUrl": item["remote_url"],
            "contentMaxAge": 1440,
            "metadataMaxAge": 1440,
        },
        "httpClient": {"blocked": False, "autoBlock": True},
        "negativeCache": {"enabled": True, "timeToLive": 1440},
        "maven": {
            "versionPolicy": item.get("version_policy", "RELEASE"),
            "layoutPolicy": item.get("layout_policy", "STRICT"),
        },
    }
    if item.get("requires_auth"):
        body["httpClient"]["authentication"] = {
            "type": "username",
            "username": lw_user,
            "password": lw_pass,
        }
    url = f"{base.rstrip('/')}/service/rest/v1/repositories/maven/proxy"
    code, resp = request("POST", url, user, password, body)
    if code in (201, 400):
        print(f"Proxy repo {name}: HTTP {code}")
    else:
        print(f"ERROR creating proxy {name}: {code} {resp}", file=sys.stderr)


def create_hosted(base: str, user: str, password: str, item: dict) -> None:
    name = item["name"]
    if repo_exists(base, user, password, name):
        print(f"Skip hosted repo (exists): {name}")
        return
    body = {
        "name": name,
        "online": True,
        "storage": {
            "blobStoreName": "default",
            "strictContentTypeValidation": True,
            "writePolicy": item.get("write_policy", "ALLOW"),
        },
        "maven": {
            "versionPolicy": item.get("version_policy", "RELEASE"),
            "layoutPolicy": item.get("layout_policy", "STRICT"),
        },
    }
    url = f"{base.rstrip('/')}/service/rest/v1/repositories/maven/hosted"
    code, resp = request("POST", url, user, password, body)
    if code in (201, 400):
        print(f"Hosted repo {name}: HTTP {code}")
    else:
        print(f"ERROR creating hosted {name}: {code} {resp}", file=sys.stderr)


def extdirect(
    base: str,
    user: str,
    password: str,
    method: str,
    data: Any,
    tid: int,
) -> tuple[int, Any]:
    """Call the capability_Capability ExtDirect endpoint the Nexus UI uses."""
    url = f"{base.rstrip('/')}/service/extdirect"
    body = {
        "action": "capability_Capability",
        "method": method,
        "data": data,
        "type": "rpc",
        "tid": tid,
    }
    return request("POST", url, user, password, body)


def list_capabilities(base: str, user: str, password: str) -> list:
    """List capabilities, preferring ExtDirect.

    /service/rest/v1/capabilities is Pro-only and 404s on Nexus OSS. Falling back
    to an empty list there makes webhook_exists() always false, so every rerun of
    this job creates a duplicate webhook and verify_webhooks() can never confirm
    anything. Read over ExtDirect first, which works on both editions.
    """
    code, data = extdirect(base, user, password, "read", None, 100)
    if code == 200 and isinstance(data, dict):
        result = data.get("result") or {}
        if result.get("success") and isinstance(result.get("data"), list):
            return result["data"]

    url = f"{base.rstrip('/')}/service/rest/v1/capabilities"
    code, data = request("GET", url, user, password)
    if code != 200:
        print(f"WARNING: could not list capabilities (REST HTTP {code})", file=sys.stderr)
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    return []


def webhook_exists(caps: list, repository: str, eda_url: str) -> bool:
    for cap in caps:
        props = cap.get("properties") or {}
        if props.get("repository") == repository and props.get("url") == eda_url:
            return True
    return False


def create_webhook_extdirect(
    base: str,
    user: str,
    password: str,
    repository: str,
    eda_url: str,
    notes: str,
    tid: int,
) -> None:
    data = [
        {
            "typeId": "webhook.repository",
            "enabled": True,
            "notes": notes,
            "properties": {
                "repository": repository,
                "names": "component",
                "url": eda_url,
                "secret": "",
            },
        }
    ]
    code, resp = extdirect(base, user, password, "create", data, tid)
    # ExtDirect answers 200 even when the RPC itself failed, so check result.success.
    ok = code == 200 and isinstance(resp, dict) and (resp.get("result") or {}).get("success")
    if ok:
        print(f"Webhook created for {repository}")
    else:
        print(f"ERROR creating webhook {repository}: HTTP {code} {resp}", file=sys.stderr)


def verify_webhooks(caps: list, repos: list[str]) -> bool:
    print("--- Webhook verification ---")
    all_ok = True
    for repo in repos:
        matches = [
            c
            for c in caps
            if (c.get("properties") or {}).get("repository") == repo
            and (c.get("typeId") == "webhook.repository" or "webhook" in str(c.get("typeId", "")))
        ]
        if not matches:
            print(f"  {repo}: not found")
            all_ok = False
            continue
        cap = matches[0]
        state = cap.get("state", "unknown")
        err = cap.get("error", False)
        print(f"  {repo}: state={state} error={err} (x{len(matches)})")
        if err or state not in ("active", "unknown"):
            all_ok = False
    return all_ok


def main() -> None:
    nexus_url = env("NEXUS_URL", required=True)
    nexus_user = env("NEXUS_USER", "admin")
    nexus_pass = env("NEXUS_ADMIN_PASSWORD", required=True)
    lw_user = env("LIGHTWELL_NETWORK_USERNAME", "")
    lw_pass = env("LIGHTWELL_NETWORK_PASSWORD", "")
    eda_url = env("EDA_WEBHOOK_URL", "")
    webhook_repos = env(
        "NEXUS_WEBHOOK_REPOSITORIES",
        "redhat-packages-validated,redhat-packages-remediated",
    )
    repos_file = env("NEXUS_REPOSITORIES_FILE", "/config/lightwell-repositories.json")
    skip_repos = env("SKIP_REPOSITORY_SETUP", "false").lower() in ("1", "true", "yes")
    skip_webhooks = env("SKIP_WEBHOOK_SETUP", "false").lower() in ("1", "true", "yes")

    wait_for_nexus(nexus_url, nexus_user, nexus_pass)
    enable_anonymous(nexus_url, nexus_user, nexus_pass)

    if not skip_repos:
        with open(repos_file, encoding="utf-8") as f:
            repositories = json.load(f)
        for item in repositories:
            if item["type"] == "proxy":
                if item.get("requires_auth") and (not lw_user or not lw_pass):
                    print(
                        f"ERROR: {item['name']} requires LIGHTWELL_NETWORK_USERNAME/PASSWORD",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                create_proxy(nexus_url, nexus_user, nexus_pass, item, lw_user, lw_pass)
            elif item["type"] == "hosted":
                create_hosted(nexus_url, nexus_user, nexus_pass, item)
            else:
                print(f"Skip unknown repo type: {item}")

    if skip_webhooks or not eda_url:
        if not eda_url:
            print("SKIP webhooks: EDA_WEBHOOK_URL not set")
        sys.exit(0)

    caps = list_capabilities(nexus_url, nexus_user, nexus_pass)
    repo_list = [r.strip() for r in webhook_repos.split(",") if r.strip()]
    tid = 1
    for repo in repo_list:
        if webhook_exists(caps, repo, eda_url):
            print(f"Skip webhook (exists): {repo} -> {eda_url}")
            continue
        create_webhook_extdirect(
            nexus_url,
            nexus_user,
            nexus_pass,
            repo,
            eda_url,
            f"SDLC EDA webhook — GitOps ({repo})",
            tid,
        )
        tid += 1

    caps = list_capabilities(nexus_url, nexus_user, nexus_pass)
    if not verify_webhooks(caps, repo_list):
        print("ERROR: EDA webhooks are not in place — SDLC flow will not fire", file=sys.stderr)
        sys.exit(1)
    print("Nexus reconcile complete.")


if __name__ == "__main__":
    main()
