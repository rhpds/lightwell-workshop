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


def enable_docker_realm(base: str, user: str, password: str) -> None:
    url = f"{base.rstrip('/')}/service/rest/v1/security/realms/active"
    code, realms = request("GET", url, user, password)
    if code != 200 or not isinstance(realms, list):
        print(f"WARNING: could not read active realms (HTTP {code})")
        return
    if "DockerToken" in realms:
        print("Docker Bearer Token Realm already active")
        return
    realms.append("DockerToken")
    code, _ = request("PUT", url, user, password, realms)
    if code in (200, 204):
        print("Docker Bearer Token Realm enabled")
    else:
        print(f"WARNING: enable Docker realm returned {code}")


def create_oci_repo(
    base: str, user: str, password: str, name: str, port: int
) -> None:
    if repo_exists(base, user, password, name):
        print(f"Skip OCI repo (exists): {name}")
        return
    body = {
        "name": name,
        "online": True,
        "storage": {
            "blobStoreName": "default",
            "strictContentTypeValidation": True,
            "writePolicy": "ALLOW",
        },
        "docker": {
            "v1Enabled": False,
            "forceBasicAuth": False,
            "httpPort": port,
        },
    }
    url = f"{base.rstrip('/')}/service/rest/v1/repositories/docker/hosted"
    code, resp = request("POST", url, user, password, body)
    if code in (201, 400):
        print(f"OCI repo {name}: HTTP {code}")
    else:
        print(f"ERROR creating OCI repo {name}: {code} {resp}", file=sys.stderr)
        sys.exit(1)


def update_maven_public_group(base: str, user: str, password: str) -> None:
    url = f"{base.rstrip('/')}/service/rest/v1/repositories/maven/group/maven-public"
    code, data = request("GET", url, user, password)
    if code != 200 or not isinstance(data, dict):
        print(f"WARNING: could not read maven-public group (HTTP {code})")
        return
    desired_members = [
        "lightwell-remediated",
        "lightwell-validated",
        "maven-releases",
        "maven-snapshots",
        "maven-central",
    ]
    current_members = data.get("group", {}).get("memberNames", [])
    if current_members == desired_members:
        print("maven-public group already configured")
        return
    data["group"]["memberNames"] = desired_members
    code, _ = request("PUT", url, user, password, data)
    if code in (200, 204):
        print(f"maven-public group updated: {desired_members}")
    else:
        print(f"WARNING: maven-public group update returned {code}")


def accept_eula(base: str, user: str, password: str) -> None:
    url = f"{base.rstrip('/')}/service/rest/v1/system/eula"
    code, data = request("GET", url, user, password)
    if code != 200 or not isinstance(data, dict):
        print(f"Note: EULA endpoint returned {code} (skipped, may be pre-3.77)")
        return
    if data.get("accepted"):
        print("EULA already accepted")
        return
    disclaimer = data.get("disclaimer", "")
    code, _ = request(
        "POST", url, user, password, {"accepted": True, "disclaimer": disclaimer}
    )
    if code in (200, 204):
        print("EULA accepted")
    else:
        print(f"WARNING: EULA accept returned {code}")


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


def proxy_body(item: dict, lw_user: str, lw_pass: str) -> dict[str, Any]:
    name = item["name"]
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
    return body


def create_proxy(
    base: str,
    user: str,
    password: str,
    item: dict,
    lw_user: str,
    lw_pass: str,
) -> None:
    name = item["name"]
    body = proxy_body(item, lw_user, lw_pass)
    repo_url = f"{base.rstrip('/')}/service/rest/v1/repositories/maven/proxy"

    if repo_exists(base, user, password, name):
        if not item.get("requires_auth"):
            print(f"Skip proxy repo (exists): {name}")
            return
        # Nexus never returns a stored password, so credential drift is impossible
        # to detect by reading. Skipping an existing repo means credentials supplied
        # after the first deploy — real Lightwell Network creds replacing the
        # placeholder — never reach the repository, and every upstream fetch keeps
        # 401ing. Push the desired auth on every run instead.
        code, resp = request("PUT", f"{repo_url}/{name}", user, password, body)
        if code in (200, 204):
            print(f"Proxy repo {name}: credentials reconciled (HTTP {code})")
        else:
            print(f"ERROR updating proxy {name}: {code} {resp}", file=sys.stderr)
            sys.exit(1)
        return

    code, resp = request("POST", repo_url, user, password, body)
    if code in (201, 400):
        print(f"Proxy repo {name}: HTTP {code}")
    else:
        print(f"ERROR creating proxy {name}: {code} {resp}", file=sys.stderr)
        sys.exit(1)


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
        sys.exit(1)


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


def webhook_exists(caps: list, repository: str, eda_urls: list[str]) -> bool:
    for cap in caps:
        props = cap.get("properties") or {}
        if props.get("repository") == repository and props.get("url") in eda_urls:
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
) -> bool:
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
        print(f"Webhook created for {repository} -> {eda_url}")
    else:
        print(f"ERROR creating webhook {repository}: HTTP {code} {resp}", file=sys.stderr)
    return bool(ok)


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


def webhook_targets(
    drive: str,
    eda_url: str,
    eda_route: str,
    listener_url: str,
    listener_route: str,
) -> list[str]:
    """ao posts to Event-Driven Ansible. tekton posts to the intake EventListener."""
    if drive == "tekton":
        chosen = (listener_url, listener_route)
    else:
        chosen = (eda_url, eda_route)
    return [url for url in chosen if url]


def main() -> None:
    nexus_url = env("NEXUS_URL", required=True)
    nexus_user = env("NEXUS_USER", "admin")
    nexus_pass = env("NEXUS_ADMIN_PASSWORD", required=True)
    lw_user = env("LIGHTWELL_NETWORK_USERNAME", "")
    lw_pass = env("LIGHTWELL_NETWORK_PASSWORD", "")
    drive = env("SDLC_DRIVE", "ao")
    eda_url = env("EDA_WEBHOOK_URL", "")
    eda_route_url = env("EDA_WEBHOOK_ROUTE_URL", "")
    listener_url = env("INTAKE_WEBHOOK_URL", "")
    listener_route = env("INTAKE_WEBHOOK_ROUTE_URL", "")
    webhook_urls = webhook_targets(drive, eda_url, eda_route_url, listener_url, listener_route)
    webhook_repos = env(
        "NEXUS_WEBHOOK_REPOSITORIES",
        "redhat-packages-validated,redhat-packages-remediated",
    )
    repos_file = env("NEXUS_REPOSITORIES_FILE", "/config/lightwell-repositories.json")
    skip_repos = env("SKIP_REPOSITORY_SETUP", "false").lower() in ("1", "true", "yes")
    skip_webhooks = env("SKIP_WEBHOOK_SETUP", "false").lower() in ("1", "true", "yes")

    oci_repo = env("NEXUS_OCI_REPO_NAME", "oci")
    oci_port = int(env("NEXUS_OCI_PORT", "5000"))

    wait_for_nexus(nexus_url, nexus_user, nexus_pass)
    accept_eula(nexus_url, nexus_user, nexus_pass)
    enable_anonymous(nexus_url, nexus_user, nexus_pass)
    enable_docker_realm(nexus_url, nexus_user, nexus_pass)
    create_oci_repo(nexus_url, nexus_user, nexus_pass, oci_repo, oci_port)
    create_hosted(nexus_url, nexus_user, nexus_pass, {
        "name": "lightwell-remediated",
        "write_policy": "ALLOW",
        "version_policy": "RELEASE",
        "layout_policy": "STRICT",
    })
    create_hosted(nexus_url, nexus_user, nexus_pass, {
        "name": "lightwell-validated",
        "write_policy": "ALLOW",
        "version_policy": "RELEASE",
        "layout_policy": "STRICT",
    })
    update_maven_public_group(nexus_url, nexus_user, nexus_pass)

    # Repos needing Lightwell Network credentials we may not have yet. The
    # tenant still has to deploy, so skip them (and their webhooks below) and
    # exit 0. Populate the Secret and re-run this Job to create them.
    skipped_repos = []

    if not skip_repos:
        with open(repos_file, encoding="utf-8") as f:
            repositories = json.load(f)
        for item in repositories:
            if item["type"] == "proxy":
                if item.get("requires_auth") and (not lw_user or not lw_pass):
                    print(
                        f"SKIP {item['name']}: LIGHTWELL_NETWORK_USERNAME/PASSWORD not set yet"
                    )
                    skipped_repos.append(item["name"])
                    continue
                create_proxy(nexus_url, nexus_user, nexus_pass, item, lw_user, lw_pass)
            elif item["type"] == "hosted":
                create_hosted(nexus_url, nexus_user, nexus_pass, item)
            else:
                print(f"Skip unknown repo type: {item}")

    if skipped_repos:
        print(
            "DEGRADED: no Lightwell Network credentials; skipped "
            + ", ".join(skipped_repos)
            + ". Populate the credentials Secret and re-run this Job."
        )

    if skip_webhooks or not webhook_urls:
        if not webhook_urls:
            print(f"SKIP webhooks: no target for sdlc.drive={drive}")
        sys.exit(0)

    caps = list_capabilities(nexus_url, nexus_user, nexus_pass)
    repo_list = [r.strip() for r in webhook_repos.split(",") if r.strip()]
    # Never attach a webhook to a repo we skipped — it does not exist, so
    # creation and the verify below would both fail and sink the whole sync.
    repo_list = [r for r in repo_list if r not in skipped_repos]
    if not repo_list:
        print("SKIP webhooks: no reconciled repositories to attach them to.")
        sys.exit(0)
    # Some Nexus deployments refuse webhook targets that resolve to a private
    # address ("Host resolves to private/local IP address(es)"), which is what
    # the in-cluster Service URL is; seen on AWS clusters. The activation's
    # Route resolves to the ingress load balancer, so fall back to it.
    tid = 1
    for repo in repo_list:
        if webhook_exists(caps, repo, webhook_urls):
            print(f"Skip webhook (exists): {repo}")
            continue
        for url in webhook_urls:
            created = create_webhook_extdirect(
                nexus_url,
                nexus_user,
                nexus_pass,
                repo,
                url,
                f"SDLC webhook — GitOps ({repo})",
                tid,
            )
            tid += 1
            if created:
                break
            if url != webhook_urls[-1]:
                print(f"Retrying webhook for {repo} with the Route URL")

    caps = list_capabilities(nexus_url, nexus_user, nexus_pass)
    if not verify_webhooks(caps, repo_list):
        print("ERROR: webhooks are not in place — SDLC flow will not fire", file=sys.stderr)
        sys.exit(1)
    print("Nexus reconcile complete.")


if __name__ == "__main__":
    main()
