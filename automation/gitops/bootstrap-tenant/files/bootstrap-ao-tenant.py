#!/usr/bin/env python3
"""Idempotent per-tenant Automation Orchestrator bootstrap.

AO isolates tenants with *projects* (not AAP organizations — there is no org
object). List APIs only return resources the caller can read, so students do
not see other tenants' workflow lists. For each lab tenant this script ensures:

  1. AO project ``lightwell-{guid}``
  2. Local AO user (project-admin on that project only); removed from the
     built-in ``users`` group so the shared ``default`` project is hidden
  3. EDA bridge service account + client_credentials in that project
  4. Published ``Lightwell Remediation`` workflow with guid-scoped EDA
     webhook paths (so tenants cannot trigger each other)
  5. Writes client_id / client_secret into a Kubernetes Secret for EDA bootstrap

Requires env:
  AO_BASE_URL, AO_ADMIN_USERNAME, AO_ADMIN_PASSWORD, GUID, USERNAME, PASSWORD
Optional:
  AO_PROJECT_NAME (default lightwell-{guid})
  AO_START_WEBHOOK_PATH / AO_RESUME_WEBHOOK_PATH
  AO_SECRET_NAME / AO_SECRET_NAMESPACE (K8s write via oc)
  VALIDATE_CERTS (default false)
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.environ.get(name, default if default is not None else "")
    if required and not val:
        print(f"ERROR: {name} is required", file=sys.stderr)
        sys.exit(1)
    return val


def make_ssl_context(validate: bool) -> ssl.SSLContext:
    if validate:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class AoClient:
    def __init__(self, base_url: str, validate_certs: bool = False) -> None:
        self.base = base_url.rstrip("/")
        self.ctx = make_ssl_context(validate_certs)
        self.token = ""

    def login(self, username: str, password: str) -> None:
        code, data = self.request(
            "POST",
            "/api/v1/auth/login",
            {"username": username, "password": password},
            auth=False,
        )
        if code != 200 or not isinstance(data, dict) or not data.get("access_token"):
            print(f"ERROR: AO login failed: {code} {data}", file=sys.stderr)
            sys.exit(1)
        self.token = data["access_token"]

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        auth: bool = True,
    ) -> tuple[int, Any]:
        url = self.base + path
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            if not self.token:
                raise RuntimeError("AO client not logged in")
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=60) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return e.code, {"raw": raw[:2000]}


def find_by_name(resources: list[dict], name: str) -> dict | None:
    for item in resources:
        if item.get("name") == name:
            return item
    return None


def list_all(client: AoClient, path: str) -> list[dict]:
    code, data = client.request("GET", path)
    if code != 200 or not isinstance(data, dict):
        print(f"ERROR: GET {path} -> {code} {data}", file=sys.stderr)
        sys.exit(1)
    return list(data.get("resources") or [])


def ensure_project(client: AoClient, name: str, description: str) -> str:
    existing = find_by_name(list_all(client, "/api/v1/projects"), name)
    if existing:
        print(f"AO project exists: {name} ({existing['id']})")
        return existing["id"]
    code, created = client.request(
        "POST",
        "/api/v1/projects",
        {"name": name, "description": description},
    )
    if code not in (200, 201) or not isinstance(created, dict) or not created.get("id"):
        print(f"ERROR: create project failed: {code} {created}", file=sys.stderr)
        sys.exit(1)
    print(f"AO project created: {name} ({created['id']})")
    return created["id"]


def ensure_user(client: AoClient, username: str, password: str, email: str) -> str:
    users = list_all(client, "/api/v1/users")
    existing = next((u for u in users if u.get("username") == username), None)
    if existing:
        print(f"AO user exists: {username} ({existing['id']})")
        return existing["id"]
    code, created = client.request(
        "POST",
        "/api/v1/users",
        {
            "username": username,
            "password": password,
            "email": email,
            "first_name": "Student",
            "last_name": username,
        },
    )
    if code not in (200, 201) or not isinstance(created, dict) or not created.get("id"):
        print(f"ERROR: create user failed: {code} {created}", file=sys.stderr)
        sys.exit(1)
    print(f"AO user created: {username} ({created['id']})")
    return created["id"]


def revoke_default_project_access(client: AoClient, user_id: str) -> None:
    """New local users join the built-in ``users`` group, which grants
    ``project-user`` on the shared ``default`` project. Remove them so each
    student only sees their tenant project (AO has no AAP-style orgs).
    """
    groups = list_all(client, "/api/v1/groups")
    users_group = next((g for g in groups if g.get("name") == "users"), None)
    if not users_group:
        print("WARNING: built-in users group not found — skip default-project revoke")
        return
    code, members = client.request("GET", f"/api/v1/groups/{users_group['id']}/members")
    if code != 200:
        print(f"WARNING: list users-group members failed: {code} {members}")
        return
    member_ids = {m.get("id") for m in (members.get("resources") or [])}
    if user_id not in member_ids:
        print("Student already outside users group (no default-project access)")
        return
    code, resp = client.request(
        "DELETE", f"/api/v1/groups/{users_group['id']}/members/{user_id}"
    )
    if code not in (200, 204):
        print(
            f"WARNING: could not remove user from users group: {code} {resp}",
            file=sys.stderr,
        )
        return
    print("Revoked default-project access (removed from users group)")


def ensure_role_assignment(
    client: AoClient, principal_id: str, role_name: str, project_id: str
) -> None:
    assignments = list_all(client, "/api/v1/role_assignments")
    for a in assignments:
        if (
            a.get("principal_id") == principal_id
            and a.get("role_name") == role_name
            and a.get("project_id") == project_id
        ):
            print(f"Role {role_name} already assigned on project")
            return
    code, created = client.request(
        "POST",
        "/api/v1/role_assignments",
        {
            "principal_id": principal_id,
            "role_name": role_name,
            "project_id": project_id,
        },
    )
    if code not in (200, 201):
        print(f"ERROR: role assignment failed: {code} {created}", file=sys.stderr)
        sys.exit(1)
    print(f"Assigned {role_name} on project")


def ensure_service_account(
    client: AoClient, project_id: str, name: str, description: str
) -> tuple[str, str, str]:
    """Return (sa_id, client_id, client_secret). Secret may be empty if reused."""
    accounts = list_all(client, "/api/v1/service_accounts")
    sa = next(
        (
            a
            for a in accounts
            if a.get("name") == name and a.get("project_id") == project_id
        ),
        None,
    )
    if not sa:
        code, created = client.request(
            "POST",
            "/api/v1/service_accounts",
            {
                "name": name,
                "description": description,
                "project_id": project_id,
            },
        )
        if code not in (200, 201) or not isinstance(created, dict) or not created.get("id"):
            print(f"ERROR: create SA failed: {code} {created}", file=sys.stderr)
            sys.exit(1)
        sa = created
        print(f"AO service account created: {name}")
    else:
        print(f"AO service account exists: {name} ({sa['id']})")

    sa_id = sa["id"]
    code, creds = client.request("GET", f"/api/v1/service_accounts/{sa_id}/credentials")
    if code != 200:
        print(f"ERROR: list credentials failed: {code} {creds}", file=sys.stderr)
        sys.exit(1)
    resources = (creds or {}).get("resources") or []
    active = next((c for c in resources if c.get("status") == "active"), None)
    if active and active.get("identifier"):
        # Secret is only returned at create time — caller may keep existing K8s secret.
        print(f"AO credential exists: {active['identifier']}")
        return sa_id, active["identifier"], ""

    code, created = client.request(
        "POST",
        f"/api/v1/service_accounts/{sa_id}/credentials",
        {"credential_type": "client_credentials"},
    )
    if code not in (200, 201) or not isinstance(created, dict):
        print(f"ERROR: create credential failed: {code} {created}", file=sys.stderr)
        sys.exit(1)
    client_id = created.get("identifier") or ""
    client_secret = created.get("client_secret") or ""
    if not client_id or not client_secret:
        print(f"ERROR: credential response missing secrets: {created}", file=sys.stderr)
        sys.exit(1)
    print(f"AO credential created: {client_id}")
    return sa_id, client_id, client_secret


def remediation_workflow_definition(
    sa_id: str, start_path: str, resume_path: str
) -> dict:
    return {
        "name": "Lightwell Remediation",
        "description": "Per-tenant Nexus→EDA→AO canvas (isolated project)",
        "schema_version": "2.0.0",
        "triggers": [
            {
                "id": "start_trigger",
                "name": "Nexus start",
                "type": "eda_trigger",
                "parameters": {
                    "webhook_path": start_path,
                    "authorized_service_account_ids": [sa_id],
                },
            },
            {
                "id": "resume_trigger",
                "name": "GitLab resume",
                "type": "eda_trigger",
                "parameters": {
                    "webhook_path": resume_path,
                    "authorized_service_account_ids": [sa_id],
                },
            },
        ],
        "nodes": [
            {
                "id": "placeholder",
                "name": "Placeholder (wire AAP JTs)",
                "type": "internal_activity",
                "parameters": {
                    "activity": "integration_health_check",
                    "input": {"batch": True},
                },
            }
        ],
        "edges": [
            {"from": "start_trigger", "to": "placeholder"},
            {"from": "resume_trigger", "to": "placeholder"},
        ],
    }


def ensure_workflow(
    client: AoClient,
    project_id: str,
    sa_id: str,
    start_path: str,
    resume_path: str,
) -> str:
    name = "Lightwell Remediation"
    workflows = list_all(client, "/api/v1/workflows")
    existing = next(
        (
            w
            for w in workflows
            if w.get("name") == name and w.get("project_id") == project_id
        ),
        None,
    )
    defn = remediation_workflow_definition(sa_id, start_path, resume_path)
    if not existing:
        code, created = client.request(
            "POST",
            "/api/v1/workflows",
            {
                "name": name,
                "description": defn["description"],
                "project_id": project_id,
                "workflow_definition": defn,
            },
        )
        if code not in (200, 201) or not isinstance(created, dict) or not created.get("id"):
            print(f"ERROR: create workflow failed: {code} {created}", file=sys.stderr)
            sys.exit(1)
        wf_id = created["id"]
        print(f"AO workflow created: {wf_id}")
    else:
        wf_id = existing["id"]
        code, patched = client.request(
            "PATCH",
            f"/api/v1/workflows/{wf_id}",
            {
                "name": name,
                "description": defn["description"],
                "workflow_definition": defn,
            },
        )
        if code not in (200, 201):
            print(f"ERROR: patch workflow failed: {code} {patched}", file=sys.stderr)
            sys.exit(1)
        print(f"AO workflow updated: {wf_id}")

    code, detail = client.request("GET", f"/api/v1/workflows/{wf_id}")
    if code != 200 or not isinstance(detail, dict):
        print(f"ERROR: get workflow failed: {code} {detail}", file=sys.stderr)
        sys.exit(1)
    if detail.get("has_validation_issues"):
        print(
            f"ERROR: workflow has validation issues: {detail.get('validation_result')}",
            file=sys.stderr,
        )
        sys.exit(1)
    if detail.get("published_version_id") and detail.get("is_enabled"):
        print("AO workflow already published")
        return wf_id
    ver = detail.get("current_version") or 1
    code, published = client.request(
        "POST",
        f"/api/v1/workflows/{wf_id}/versions/{ver}/publish",
        {
            "publish_name": f"tenant-{start_path}",
            "change_description": "Per-tenant Lightwell remediation",
        },
    )
    if code not in (200, 201):
        print(f"ERROR: publish workflow failed: {code} {published}", file=sys.stderr)
        sys.exit(1)
    print(f"AO workflow published (version {ver})")
    return wf_id


def write_k8s_secret(
    namespace: str,
    name: str,
    client_id: str,
    client_secret: str,
    project_name: str,
) -> None:
    """Create/update Secret. If client_secret empty, preserve existing secret data."""
    if not client_secret:
        # Reuse existing secret if present and client_id matches.
        try:
            out = subprocess.check_output(
                [
                    "oc",
                    "get",
                    "secret",
                    name,
                    "-n",
                    namespace,
                    "-o",
                    "json",
                ],
                text=True,
            )
            data = json.loads(out).get("data") or {}
            import base64

            existing_id = base64.b64decode(data.get("client_id", "")).decode()
            if existing_id == client_id and data.get("client_secret"):
                print(f"K8s secret {namespace}/{name} already has credentials — kept")
                return
        except subprocess.CalledProcessError:
            print(
                "ERROR: credential secret missing and AO did not return a new "
                "client_secret (rotate by deleting the SA credential)",
                file=sys.stderr,
            )
            sys.exit(1)
        print(
            "ERROR: existing K8s secret client_id mismatch and no new secret from AO",
            file=sys.stderr,
        )
        sys.exit(1)

    subprocess.check_call(
        [
            "oc",
            "create",
            "secret",
            "generic",
            name,
            "-n",
            namespace,
            f"--from-literal=client_id={client_id}",
            f"--from-literal=client_secret={client_secret}",
            f"--from-literal=project_name={project_name}",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        stdout=open("/tmp/ao-secret.yaml", "w"),
    )
    subprocess.check_call(["oc", "apply", "-f", "/tmp/ao-secret.yaml"])
    print(f"Wrote K8s secret {namespace}/{name}")


def main() -> None:
    base = env("AO_BASE_URL", required=True)
    admin_user = env("AO_ADMIN_USERNAME", "admin")
    admin_pass = env("AO_ADMIN_PASSWORD", required=True)
    guid = env("GUID", required=True)
    username = env("USERNAME", required=True)
    password = env("PASSWORD", required=True)
    project_name = env("AO_PROJECT_NAME", f"lightwell-{guid}")
    start_path = env(
        "AO_START_WEBHOOK_PATH", f"lightwell-remediation-start-{guid}"
    )
    resume_path = env(
        "AO_RESUME_WEBHOOK_PATH", f"lightwell-remediation-resume-{guid}"
    )
    secret_name = env("AO_SECRET_NAME", "automation-orchestrator")
    secret_ns = env("AO_SECRET_NAMESPACE", required=True)
    validate = env("VALIDATE_CERTS", "false").lower() in ("1", "true", "yes")

    client = AoClient(base, validate_certs=validate)
    client.login(admin_user, admin_pass)

    project_id = ensure_project(
        client,
        project_name,
        f"Isolated Lightwell remediation project for tenant {guid}",
    )
    user_id = ensure_user(
        client, username, password, f"{username}@lightwell.lab"
    )
    revoke_default_project_access(client, user_id)
    ensure_role_assignment(client, user_id, "project-admin", project_id)

    sa_id, client_id, client_secret = ensure_service_account(
        client,
        project_id,
        "lightwell-eda-bridge",
        f"EDA bridge for tenant {guid}",
    )
    ensure_workflow(client, project_id, sa_id, start_path, resume_path)
    write_k8s_secret(secret_ns, secret_name, client_id, client_secret, project_name)

    print(
        f"AO tenant ready: project={project_name} user={username} "
        f"start_path={start_path} resume_path={resume_path}"
    )


if __name__ == "__main__":
    main()
