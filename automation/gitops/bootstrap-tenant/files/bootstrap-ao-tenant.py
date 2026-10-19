#!/usr/bin/env python3
"""Idempotent per-tenant Automation Orchestrator bootstrap.

AO isolates tenants with *projects* (not AAP organizations — there is no org
object). List APIs only return resources the caller can read, so students do
not see other tenants' workflow lists. For each lab tenant this script ensures:

  1. AO project ``lightwell-{guid}``
  2. Local AO user (project-admin on that project only); removed from the
     built-in ``users`` group so the shared ``default`` project is hidden
  3. EDA bridge service account + client_credentials in that project
  4. AO credential for AAP Controller (launch job templates)
  5. Three published workflows (one eda_trigger each), no Approval *gates*:
       Start  — Nexus → Prepare → for-each Impact/Verifier; auto_approve → AO merge
                (ADR-040/041); needs_approval stays open for student merge
       Merged — GitLab MR merged → SNOW → poll PaC build → SNOW build (ADR-039)
       Deploy — Argo health → SNOW lifecycle + finalize
  6. Writes client_id / client_secret into a Kubernetes Secret for EDA bootstrap
  7. Retires legacy monolith + retired Build workflow (unpublish + disable)

Requires env:
  AO_BASE_URL, AO_ADMIN_USERNAME, AO_ADMIN_PASSWORD, GUID, USERNAME, PASSWORD
  AAP_ADMIN_USERNAME, AAP_ADMIN_PASSWORD (Controller API for aap_job_template nodes)
Optional:
  AO_PROJECT_NAME (default lightwell-{guid})
  AO_START_WEBHOOK_PATH / AO_MERGED_WEBHOOK_PATH / AO_DEPLOY_WEBHOOK_PATH
  (defaults lightwell-remediation-{start,merged,deploy}-{guid})
  AAP_ORGANIZATION_NAME (default user-{guid})
  AO_SECRET_NAME / AO_SECRET_NAMESPACE (K8s write via oc)
  VALIDATE_CERTS (default false)
  GITLAB_URL / GITLAB_TOKEN (baked into Merged poll + SNOW lifecycle)
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


# AO local-user policy (seen on create): password min length 14.
AO_USER_PASSWORD_MIN_LEN = 14


def ensure_user(client: AoClient, username: str, password: str, email: str) -> str:
    users = list_all(client, "/api/v1/users")
    existing = next((u for u in users if u.get("username") == username), None)
    if existing:
        print(f"AO user exists: {username} ({existing['id']})")
        return existing["id"]
    if len(password) < AO_USER_PASSWORD_MIN_LEN:
        print(
            f"ERROR: AO user password is {len(password)} chars; AO requires "
            f">= {AO_USER_PASSWORD_MIN_LEN}. Set tenant chart value `password` "
            f"(or AO_PASSWORD) longer and re-run ao-bootstrap.",
            file=sys.stderr,
        )
        sys.exit(1)
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


AAP_CREDENTIAL_TYPE_NAME = "Ansible Automation Platform"
AAP_CREDENTIAL_NAME = "AAP Controller"
JT_QUERY_TPA = "SDLC Query TPA"
JT_IMPACT = "SDLC Trigger Impact Analyzer"
JT_MR_VERIFIER = "SDLC Trigger MR Verifier"
JT_SNOW_CREATE = "SDLC Create SNOW Incident"
JT_CLASSIFY = "SDLC Classify Affected Apps"
JT_SNOW_COMMENT = "SDLC SNOW Comment"
JT_SNOW_PARENT_STATUS = "SDLC SNOW Parent Status"
JT_SNOW_CHILDREN = "SDLC SNOW Create Children"
JT_PREPARE = "SDLC Prepare Remediation"
JT_SNOW_ITER = "SDLC SNOW Iteration Comment"
JT_SNOW_LIFECYCLE = "SDLC SNOW Lifecycle Event"
JT_SNOW_FINALIZE = "SDLC SNOW Finalize"
JT_POLL_BUILD = "SDLC Poll Build Status"
JT_MERGE = "SDLC Merge GitLab MR"
AAP_INTEGRATION_NAME = "AAP Lightwell"


def ensure_aap_integration(
    client: AoClient,
    *,
    aap_base_url: str,
    management_credential_id: str,
) -> str:
    """Create/reuse a global Ansible Automation Platform integration.

    aap_job_template nodes require a configured AAP integration (endpoint URL).
    The workflow node's credential_id is separate runtime auth; this integration
    supplies the Controller base URL + health-check credential.
    """
    integrations = list_all(client, "/api/v1/integrations")
    existing = next(
        (
            i
            for i in integrations
            if i.get("name") == AAP_INTEGRATION_NAME
            and i.get("integration_type") == "ansible_automation_platform"
        ),
        None,
    )
    if existing:
        print(f"AO AAP integration exists: {existing['id']}")
        return existing["id"]

    base = aap_base_url.rstrip("/")
    code, created = client.request(
        "POST",
        "/api/v1/integrations",
        {
            "name": AAP_INTEGRATION_NAME,
            "description": "Shared AAP Controller for Lightwell remediation JTs",
            "integration_type": "ansible_automation_platform",
            "configuration": {
                "integration_type": "ansible_automation_platform",
                "base_url": base,
                "insecure_skip_tls_verify": True,
            },
            "management_credential_id": management_credential_id,
            "enabled": True,
            "scope": "global",
        },
    )
    if code not in (200, 201) or not isinstance(created, dict) or not created.get("id"):
        print(f"ERROR: create AAP integration failed: {code} {created}", file=sys.stderr)
        print(
            "Hint: APP_INTEGRATION_URL_ALLOWED_HOSTS must include the AAP hostname "
            "when it resolves to a private/router IP.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"AO AAP integration created: {created['id']}")
    return created["id"]


def ensure_aap_credential(
    client: AoClient,
    project_id: str,
    *,
    username: str,
    password: str,
) -> str:
    """Create/reuse an AO credential that can launch AAP job templates."""
    types = list_all(client, "/api/v1/credential_types")
    ctype = find_by_name(types, AAP_CREDENTIAL_TYPE_NAME)
    if not ctype or not ctype.get("id"):
        print(
            f"ERROR: credential type {AAP_CREDENTIAL_TYPE_NAME!r} not found",
            file=sys.stderr,
        )
        sys.exit(1)

    creds = list_all(client, "/api/v1/credentials")
    existing = next(
        (
            c
            for c in creds
            if c.get("name") == AAP_CREDENTIAL_NAME
            and c.get("project_id") == project_id
        ),
        None,
    )
    if existing:
        print(f"AO AAP credential exists: {existing['id']}")
        return existing["id"]

    code, created = client.request(
        "POST",
        "/api/v1/credentials",
        {
            "name": AAP_CREDENTIAL_NAME,
            "description": "Controller API auth for Lightwell remediation JTs",
            "credential_type_id": ctype["id"],
            "project_id": project_id,
            "inputs": {"username": username, "password": password},
        },
    )
    if code not in (200, 201) or not isinstance(created, dict) or not created.get("id"):
        print(f"ERROR: create AAP credential failed: {code} {created}", file=sys.stderr)
        sys.exit(1)
    print(f"AO AAP credential created: {created['id']}")
    return created["id"]


def _aap_jt_node(
    node_id: str,
    name: str,
    job_template_name: str,
    organization_name: str,
    credential_id: str,
    extra_vars: dict[str, Any],
    *,
    integration_id: str = "",
    continue_on_failure: bool = False,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "job_template_name": job_template_name,
        "organization_name": organization_name,
        "credential_id": credential_id,
        "extra_vars": extra_vars,
    }
    if integration_id:
        params["integration_id"] = integration_id
    node: dict[str, Any] = {
        "id": node_id,
        "name": name,
        "type": "aap_job_template",
        "parameters": params,
    }
    # AO schema: continue_on_failure lives under settings, not top-level.
    if continue_on_failure:
        node["settings"] = {"continue_on_failure": True}
    return node


WF_START = "Lightwell Remediation — Start"
WF_MERGED = "Lightwell Remediation — Merged"
WF_BUILD = "Lightwell Remediation — Build"  # retired ADR-039
WF_DEPLOY = "Lightwell Remediation — Deploy"
LEGACY_MONOLITH_NAMES = (
    "Lightwell Remediation",  # pre-split single/multi-trigger canvas
    WF_BUILD,  # PipelineRun webhook canvas — merged into WF_MERGED (ADR-039)
)


def _eda_trigger(sa_id: str, webhook_path: str, *, name: str = "EDA webhook") -> dict:
    return {
        "id": "eda_trigger",
        "name": name,
        "type": "eda_trigger",
        "parameters": {
            "webhook_path": webhook_path,
            "authorized_service_account_ids": [sa_id],
        },
    }


def _trigger_common() -> dict:
    """Shared ${trigger.*} extras baked with snow/gitlab/tpa/opencode secrets when present.

    OpenCode Basic auth must be baked (same class of bug as empty snow_url):
    EDA job_args often omit opencode_server_password; Impact then 401s on
    POST /session (seen on cng2l AO Start smoke).
    """
    snow_url = env("SNOW_URL", "")
    snow_svc_url = env("SNOW_SVC_URL", "")
    gitlab_token = env("GITLAB_TOKEN", "")
    tpa_oauth_client_secret = env("TPA_OAUTH_CLIENT_SECRET", "")
    opencode_base_url = env("OPENCODE_BASE_URL", "")
    opencode_ui_url = env("OPENCODE_UI_URL", "")
    opencode_user = env("OPENCODE_SERVER_USERNAME", "opencode")
    opencode_password = env("OPENCODE_SERVER_PASSWORD", "")
    return {
        "artifact_name": "${trigger.artifact_name}",
        "artifact_group": "${trigger.artifact_group}",
        "artifact_version": "${trigger.artifact_version}",
        "package_purl": "${trigger.package_purl}",
        "vulnerable_version": "${trigger.vulnerable_version}",
        "fix_version": "${trigger.fix_version}",
        "cve_id": "${trigger.cve_id}",
        "severity": "${trigger.severity}",
        "tpa_url": "${trigger.tpa_url}",
        "keycloak_url": "${trigger.keycloak_url}",
        "keycloak_tpa_realm": "${trigger.keycloak_tpa_realm}",
        "tpa_uploader_username": "${trigger.tpa_uploader_username}",
        "tpa_oauth_client_id": "${trigger.tpa_oauth_client_id}",
        "tpa_oauth_client_secret": (
            tpa_oauth_client_secret
            if tpa_oauth_client_secret
            else "${trigger.tpa_oauth_client_secret}"
        ),
        "tpa_uploader_password": "${trigger.tpa_uploader_password}",
        "tpa_sbom_label": "${trigger.tpa_sbom_label}",
        "gitlab_url": "${trigger.gitlab_url}",
        "remediation_app_gitlab_path": "${trigger.remediation_app_gitlab_path}",
        "eda_webhook_url": "${trigger.eda_webhook_url}",
        "opencode_base_url": (
            opencode_base_url
            if opencode_base_url
            else "${trigger.opencode_base_url}"
        ),
        # Browser Route (ui-gate). Impact builds …/global/session/{id} deep links.
        "opencode_ui_url": (
            opencode_ui_url
            if opencode_ui_url
            else "${trigger.opencode_ui_url}"
        ),
        "opencode_server_username": (
            opencode_user if opencode_user else "${trigger.opencode_server_username}"
        ),
        "opencode_server_password": (
            opencode_password
            if opencode_password
            else "${trigger.opencode_server_password}"
        ),
        "blast_radius_mode": "${trigger.blast_radius_mode}",
        "aap_organization_name": "${trigger.aap_organization_name}",
        "snow_url": snow_url if snow_url else "${trigger.snow_url}",
        "snow_svc_url": snow_svc_url if snow_svc_url else "${trigger.snow_svc_url}",
        "gitlab_token": gitlab_token if gitlab_token else "${trigger.gitlab_token}",
        "guid": "${trigger.guid}",
    }


def _lifecycle_common() -> dict:
    snow_url = env("SNOW_URL", "")
    snow_svc_url = env("SNOW_SVC_URL", "")
    gitlab_url = env("GITLAB_URL", "")
    gitlab_token = env("GITLAB_TOKEN", "")
    argo_cd_url = env("ARGO_CD_URL", "")
    argo_app_name = env("ARGO_APP_NAME", "")
    argo_app_ns = env("ARGO_APP_NAMESPACE", "openshift-gitops")
    console_url = env("OPENSHIFT_CONSOLE_URL", "")
    apps_namespace = env("APPS_NAMESPACE", "")
    apps_domain = env("APPS_DOMAIN", "")
    return {
        "snow_url": snow_url if snow_url else "${trigger.snow_url}",
        "snow_svc_url": snow_svc_url if snow_svc_url else "${trigger.snow_svc_url}",
        "guid": "${trigger.guid}",
        "gitlab_path": "${trigger.gitlab_path}",
        "merge_request_iid": "${trigger.merge_request_iid}",
        # Omit merge_commit_sha — often absent on trigger (AO property error).
        # Poll-build resolves SHA from MR; Deploy never needs it.
        "project_id": "${trigger.project_id}",
        "gitlab_url": gitlab_url if gitlab_url else "${trigger.gitlab_url}",
        "gitlab_token": gitlab_token if gitlab_token else "${trigger.gitlab_token}",
        "child_incident": "${trigger.child_incident}",
        "parent_incident": "${trigger.parent_incident}",
        "snow_incident": "${trigger.snow_incident}",
        "build_status": "${trigger.status}",
        "deploy_health": "${trigger.health}",
        "signal_source": "${trigger.signal_source}",
        # Baked Acme Application name; bridge may also send trigger.argo_app.
        "argo_app": argo_app_name if argo_app_name else "${trigger.argo_app}",
        "argo_cd_url": argo_cd_url if argo_cd_url else "${trigger.argo_cd_url}",
        "argo_app_namespace": argo_app_ns,
        "openshift_console_url": (
            console_url if console_url else "${trigger.openshift_console_url}"
        ),
        "apps_namespace": (
            apps_namespace if apps_namespace else "${trigger.apps_namespace}"
        ),
        "apps_domain": apps_domain if apps_domain else "${trigger.apps_domain}",
    }


def start_workflow_definition(
    sa_id: str,
    start_path: str,
    *,
    aap_org: str,
    aap_credential_id: str,
    aap_integration_id: str = "",
) -> dict:
    """Nexus start → prepare (SNOW/TPA/classify/children) → apps_loop."""
    trigger_common = _trigger_common()
    prepare_vars = {**trigger_common}
    parent_inc = "${prepare.artifacts.parent_incident}"
    impact_vars = {
        **trigger_common,
        "package_info": "${prepare.artifacts.package_info}",
        "app_item": "${loop.item}",
        "affected_repos": ["${loop.item}"],
        "blast_radius": {"mode": "tpa_affected_repos", "count": 1},
        "snow_incident": "${loop.item.child_incident}",
        "child_incident": "${loop.item.child_incident}",
        "parent_incident": parent_inc,
    }
    verifier_vars = {
        **trigger_common,
        "merge_request_iid": "${impact.artifacts.merge_request_iid}",
        "project_id": "${impact.artifacts.project_id}",
        "gitlab_path": "${impact.artifacts.gitlab_path}",
        "approval": "${impact.artifacts.approval}",
        "source_branch": "${impact.artifacts.source_branch}",
        "target_branch": "${impact.artifacts.target_branch}",
        "repository_git_url": "${impact.artifacts.repository_git_url}",
        "snow_incident": "${loop.item.child_incident}",
        "child_incident": "${loop.item.child_incident}",
        "parent_incident": parent_inc,
    }
    # Bake gitlab_url for Merge JT + SNOW comment URL synthesis (EDA often omits it).
    gitlab_url = env("GITLAB_URL", "")
    gitlab_url_var = gitlab_url if gitlab_url else "${trigger.gitlab_url}"
    iter_comment_base = {
        "snow_url": trigger_common["snow_url"],
        "snow_svc_url": trigger_common["snow_svc_url"],
        "snow_incident": "${loop.item.child_incident}",
        "child_incident": "${loop.item.child_incident}",
        "parent_incident": parent_inc,
        "gitlab_url": gitlab_url_var,
        "gitlab_path": "${verifier.artifacts.gitlab_path}",
        "approval": "${verifier.artifacts.approval}",
        "merge_request_iid": "${verifier.artifacts.merge_request_iid}",
        "merge_request_url": "${impact.artifacts.merge_request_url}",
        "opencode_session_id": "${impact.artifacts.opencode_session_id}",
        "opencode_session_ui_url": "${impact.artifacts.opencode_session_ui_url}",
        "opencode_session_title": "${impact.artifacts.opencode_session_title}",
        "opencode_session_summary": "${impact.artifacts.opencode_session_summary}",
        "opencode_ui_url": trigger_common["opencode_ui_url"],
        "verifier_status": "${verifier.artifacts.verifier_status}",
        "guid": "${trigger.guid}",
    }
    iter_comment_already = {
        "snow_url": trigger_common["snow_url"],
        "snow_svc_url": trigger_common["snow_svc_url"],
        "snow_incident": "${loop.item.child_incident}",
        "child_incident": "${loop.item.child_incident}",
        "parent_incident": parent_inc,
        "gitlab_url": gitlab_url_var,
        "gitlab_path": "${impact.artifacts.gitlab_path}",
        "approval": "${impact.artifacts.approval}",
        "merge_request_iid": "${impact.artifacts.merge_request_iid}",
        "merge_request_url": "${impact.artifacts.merge_request_url}",
        "opencode_session_id": "${impact.artifacts.opencode_session_id}",
        "opencode_session_ui_url": "${impact.artifacts.opencode_session_ui_url}",
        "opencode_session_title": "${impact.artifacts.opencode_session_title}",
        "opencode_session_summary": "${impact.artifacts.opencode_session_summary}",
        "opencode_ui_url": trigger_common["opencode_ui_url"],
        "verifier_status": "n/a",
        "guid": "${trigger.guid}",
        "iteration_outcome": "already_current",
    }
    merge_vars = {
        "gitlab_url": gitlab_url_var,
        "gitlab_token": trigger_common["gitlab_token"],
        "gitlab_path": "${verifier.artifacts.gitlab_path}",
        "merge_request_iid": "${verifier.artifacts.merge_request_iid}",
        "project_id": "${verifier.artifacts.project_id}",
        "guid": "${trigger.guid}",
        "validate_certs": False,
        # ADR-050: merge-gitlab-mr.yml waits for the build-pull-request check
        # on the MR head before merging, so check and merge stay atomic in one
        # node. That wait also leaves the MR visibly open for ~110s, which is
        # the demo window the old fixed merge_delay_seconds pause provided.
    }
    parent_awaiting_vars = {
        "snow_url": trigger_common["snow_url"],
        "snow_svc_url": trigger_common["snow_svc_url"],
        "snow_ui_base": trigger_common["snow_url"],
        "parent_incident": parent_inc,
        "snow_incident": parent_inc,
        "guid": "${trigger.guid}",
        "parent_status_headline": "Start workflow finished",
        "parent_status_plain": (
            "The remediation **Start** workflow finished. "
            "Open each **child** ticket for MR, verifier, merge, build, and deploy detail. "
            "auto_approve apps may already be merged; needs_approval apps wait for a GitLab merge."
        ),
    }
    return {
        "name": WF_START,
        "description": (
            "Nexus/EDA start: Prepare Remediation → for-each (Impact → "
            "Verifier → auto_approve merge or leave MR open for student). "
            "No AO Approval gates."
        ),
        "schema_version": "2.0.0",
        "triggers": [
            _eda_trigger(sa_id, start_path, name="Nexus start"),
        ],
        "nodes": [
            _aap_jt_node(
                "prepare",
                "Prepare remediation",
                JT_PREPARE,
                aap_org,
                aap_credential_id,
                prepare_vars,
                integration_id=aap_integration_id,
            ),
            {
                "id": "apps_loop",
                "name": "Remediate AO apps",
                "type": "loop",
                "parameters": {
                    "type": "for_each",
                    "items": "${prepare.artifacts.ao_apps}",
                    "max_iterations": 10,
                },
                "settings": {"continue_on_failure": True},
            },
            _aap_jt_node(
                "impact",
                "Impact Analyzer",
                JT_IMPACT,
                aap_org,
                aap_credential_id,
                impact_vars,
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            {
                "id": "impact_already",
                "name": "Already current?",
                "type": "condition",
                "parameters": {
                    "condition": (
                        '${impact.artifacts.iteration_outcome} == "already_current"'
                    ),
                },
            },
            _aap_jt_node(
                "verifier",
                "MR Verifier",
                JT_MR_VERIFIER,
                aap_org,
                aap_credential_id,
                verifier_vars,
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            {
                "id": "verifier_ok",
                "name": "Verifier passed?",
                "type": "condition",
                "parameters": {
                    "condition": (
                        '${verifier.artifacts.iteration_outcome} == "verifier_pass"'
                    ),
                },
            },
            {
                "id": "approval_auto",
                "name": "Auto-approve?",
                "type": "condition",
                "parameters": {
                    # Prefer loop.item (classify); fall back if Impact rewrote it.
                    "condition": (
                        '${loop.item.approval} == "auto_approve"'
                    ),
                },
            },
            _aap_jt_node(
                "merge_auto",
                "Merge GitLab MR (auto_approve)",
                JT_MERGE,
                aap_org,
                aap_credential_id,
                merge_vars,
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "snow_iter_auto_merged",
                "SNOW — AO auto-merged",
                JT_SNOW_ITER,
                aap_org,
                aap_credential_id,
                {**iter_comment_base, "iteration_outcome": "merged"},
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "snow_iter_mr_ready",
                "SNOW — MR ready (merge in GitLab)",
                JT_SNOW_ITER,
                aap_org,
                aap_credential_id,
                {**iter_comment_base, "iteration_outcome": "awaiting_merge"},
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "snow_iter_already",
                "SNOW iteration (already current)",
                JT_SNOW_ITER,
                aap_org,
                aap_credential_id,
                iter_comment_already,
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "snow_iter_fail",
                "SNOW iteration (verifier fail)",
                JT_SNOW_ITER,
                aap_org,
                aap_credential_id,
                {**iter_comment_base, "iteration_outcome": "verifier_fail"},
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "snow_parent_awaiting",
                "SNOW parent — Start finished",
                JT_SNOW_PARENT_STATUS,
                aap_org,
                aap_credential_id,
                parent_awaiting_vars,
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
        ],
        "edges": [
            {"from": "eda_trigger", "to": "prepare"},
            {"from": "prepare", "to": "apps_loop"},
            {"from": "apps_loop", "to": "impact", "from_port": "iterate"},
            {"from": "impact", "to": "impact_already"},
            {
                "from": "impact_already",
                "to": "snow_iter_already",
                "from_port": "true",
            },
            {"from": "impact_already", "to": "verifier", "from_port": "false"},
            {"from": "verifier", "to": "verifier_ok"},
            {
                "from": "verifier_ok",
                "to": "approval_auto",
                "from_port": "true",
            },
            {"from": "verifier_ok", "to": "snow_iter_fail", "from_port": "false"},
            {
                "from": "approval_auto",
                "to": "merge_auto",
                "from_port": "true",
            },
            {
                "from": "approval_auto",
                "to": "snow_iter_mr_ready",
                "from_port": "false",
            },
            {"from": "merge_auto", "to": "snow_iter_auto_merged"},
            {
                "from": "apps_loop",
                "to": "snow_parent_awaiting",
                "from_port": "complete",
            },
        ],
    }


def merged_workflow_definition(
    sa_id: str,
    merged_path: str,
    *,
    aap_org: str,
    aap_credential_id: str,
    aap_integration_id: str = "",
) -> dict:
    """MR merged → SNOW merged → poll PaC build → SNOW build (ADR-039)."""
    lc = _lifecycle_common()
    poll_vars = {
        "gitlab_url": lc["gitlab_url"],
        "gitlab_token": lc["gitlab_token"],
        "gitlab_path": "${trigger.gitlab_path}",
        "merge_request_iid": "${trigger.merge_request_iid}",
        "project_id": "${trigger.project_id}",
        "guid": "${trigger.guid}",
        "validate_certs": False,
    }
    build_lc = {
        **lc,
        "build_status": "${poll_build.artifacts.status}",
        "status": "${poll_build.artifacts.status}",
        "build_url": "${poll_build.artifacts.build_url}",
        "signal_source": "ao_poll_gitlab_pac",
    }
    return {
        "name": WF_MERGED,
        "description": (
            "GitLab MR merged → SNOW lifecycle → poll PaC push build → "
            "SNOW build succeeded/failed (per gitlab_path)."
        ),
        "schema_version": "2.0.0",
        "triggers": [_eda_trigger(sa_id, merged_path, name="GitLab MR merged")],
        "nodes": [
            _aap_jt_node(
                "lc_merged",
                "SNOW — MR merged",
                JT_SNOW_LIFECYCLE,
                aap_org,
                aap_credential_id,
                {**lc, "iteration_outcome": "merged"},
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "poll_build",
                "Poll PaC build status",
                JT_POLL_BUILD,
                aap_org,
                aap_credential_id,
                poll_vars,
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            {
                "id": "build_ok",
                "name": "Build succeeded?",
                "type": "condition",
                "parameters": {
                    "condition": '${poll_build.artifacts.status} == "Succeeded"',
                },
            },
            _aap_jt_node(
                "lc_build_ok",
                "SNOW — build succeeded",
                JT_SNOW_LIFECYCLE,
                aap_org,
                aap_credential_id,
                {**build_lc, "iteration_outcome": "build_succeeded"},
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "lc_build_fail",
                "SNOW — build failed",
                JT_SNOW_LIFECYCLE,
                aap_org,
                aap_credential_id,
                {
                    **build_lc,
                    "iteration_outcome": "build_failed",
                    # Comment SNOW, then fail the JT so the AO run is Failed.
                    "fail_on_bad_outcome": True,
                },
                integration_id=aap_integration_id,
                continue_on_failure=False,
            ),
        ],
        "edges": [
            {"from": "eda_trigger", "to": "lc_merged"},
            {"from": "lc_merged", "to": "poll_build"},
            {"from": "poll_build", "to": "build_ok"},
            {"from": "build_ok", "to": "lc_build_ok", "from_port": "true"},
            {"from": "build_ok", "to": "lc_build_fail", "from_port": "false"},
        ],
    }


def deploy_workflow_definition(
    sa_id: str,
    deploy_path: str,
    *,
    aap_org: str,
    aap_credential_id: str,
    aap_integration_id: str = "",
) -> dict:
    lc = _lifecycle_common()
    finalize_vars = {
        "snow_url": lc["snow_url"],
        "snow_svc_url": lc["snow_svc_url"],
        # Deploy EDA payload has no parent — lc_deployed looks up by gitlab_path
        # and exports it (must be non-empty; AAP drops "").
        "parent_incident": "${lc_deployed.artifacts.parent_incident}",
        "snow_incident": "${lc_deployed.artifacts.parent_incident}",
        "guid": "${trigger.guid}",
        "gitlab_path": "${trigger.gitlab_path}",
        "argo_app": lc["argo_app"],
        "argo_cd_url": lc["argo_cd_url"],
        "argo_app_namespace": lc["argo_app_namespace"],
        "openshift_console_url": lc["openshift_console_url"],
        "apps_namespace": lc["apps_namespace"],
        "apps_domain": lc["apps_domain"],
    }
    return {
        "name": WF_DEPLOY,
        "description": "Argo health → SNOW deploy + parent finalize when Healthy.",
        "schema_version": "2.0.0",
        "triggers": [_eda_trigger(sa_id, deploy_path, name="Deploy health")],
        "nodes": [
            {
                "id": "deploy_ok",
                "name": "Deploy Healthy?",
                "type": "condition",
                "parameters": {
                    "condition": '${trigger.health} == "Healthy"',
                },
            },
            _aap_jt_node(
                "lc_deployed",
                "SNOW — deploy Healthy",
                JT_SNOW_LIFECYCLE,
                aap_org,
                aap_credential_id,
                {**lc, "iteration_outcome": "deployed"},
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "lc_deploy_fail",
                "SNOW — deploy failed",
                JT_SNOW_LIFECYCLE,
                aap_org,
                aap_credential_id,
                {**lc, "iteration_outcome": "deploy_failed"},
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "snow_finalize",
                "SNOW finalize (parent)",
                JT_SNOW_FINALIZE,
                aap_org,
                aap_credential_id,
                finalize_vars,
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
        ],
        "edges": [
            {"from": "eda_trigger", "to": "deploy_ok"},
            {"from": "deploy_ok", "to": "lc_deployed", "from_port": "true"},
            {"from": "deploy_ok", "to": "lc_deploy_fail", "from_port": "false"},
            {"from": "lc_deployed", "to": "snow_finalize"},
        ],
    }


def retire_legacy_workflows(client: "AoClient", project_id: str) -> None:
    """Unpublish/disable pre-split monolith so webhook paths can be reused."""
    workflows = list_all(client, "/api/v1/workflows")
    for w in workflows:
        if w.get("project_id") != project_id:
            continue
        if w.get("name") not in LEGACY_MONOLITH_NAMES:
            continue
        wf_id = w["id"]
        print(f"Retiring legacy AO workflow {w.get('name')!r} ({wf_id[:8]}…)")
        code, _ = client.request("POST", f"/api/v1/workflows/{wf_id}/unpublish", {})
        print(f"  unpublish → {code}")
        code, _ = client.request(
            "PATCH", f"/api/v1/workflows/{wf_id}", {"is_enabled": False}
        )
        print(f"  disable → {code}")


def ensure_workflow(
    client: "AoClient",
    project_id: str,
    defn: dict,
) -> str:
    """Create/patch/publish one workflow from a full definition dict."""
    name = defn["name"]
    webhook_path = defn["triggers"][0]["parameters"]["webhook_path"]
    workflows = list_all(client, "/api/v1/workflows")
    existing = next(
        (
            w
            for w in workflows
            if w.get("name") == name and w.get("project_id") == project_id
        ),
        None,
    )
    code, validated = client.request(
        "POST", "/api/v1/workflows/validate", {"workflow_definition": defn}
    )
    result = validated if isinstance(validated, dict) else {}
    if code != 200 or result.get("is_valid") is False:
        print(f"ERROR: {name} invalid: {code} {validated}", file=sys.stderr)
        sys.exit(1)

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
            print(f"ERROR: create {name} failed: {code} {created}", file=sys.stderr)
            sys.exit(1)
        wf_id = created["id"]
        print(f"AO workflow created: {name} ({wf_id})")
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
            print(f"ERROR: patch {name} failed: {code} {patched}", file=sys.stderr)
            sys.exit(1)
        print(f"AO workflow updated: {name} ({wf_id})")

    code, detail = client.request("GET", f"/api/v1/workflows/{wf_id}")
    if code != 200 or not isinstance(detail, dict):
        print(f"ERROR: get {name} failed: {code} {detail}", file=sys.stderr)
        sys.exit(1)
    if detail.get("has_validation_issues"):
        print(
            f"ERROR: {name} validation issues: {detail.get('validation_result')}",
            file=sys.stderr,
        )
        sys.exit(1)

    ver = detail.get("current_version") or 1
    published_ver = detail.get("published_version_number")
    code, published = client.request(
        "POST",
        f"/api/v1/workflows/{wf_id}/versions/{ver}/publish",
        {
            "publish_name": f"tenant-{webhook_path}",
            "change_description": f"Per-tenant {name}",
        },
    )
    if code in (200, 201):
        print(f"AO workflow published: {name} (version {ver})")
        return wf_id
    if published_ver == ver and detail.get("is_enabled"):
        print(f"AO workflow already published: {name} (version {ver})")
        return wf_id
    # Path still held by a previously_published version — unpublish then retry.
    detail_s = str(published)
    if "WEBHOOK_TRIGGER_PATH_CONFLICT" in detail_s or code == 409:
        print(f"Path conflict publishing {name} — unpublish + retry")
        client.request("POST", f"/api/v1/workflows/{wf_id}/unpublish", {})
        code, published = client.request(
            "POST",
            f"/api/v1/workflows/{wf_id}/versions/{ver}/publish",
            {
                "publish_name": f"tenant-{webhook_path}",
                "change_description": f"Per-tenant {name} (retry)",
            },
        )
        if code in (200, 201):
            print(f"AO workflow published after unpublish: {name} (version {ver})")
            return wf_id
    print(f"ERROR: publish {name} failed: {code} {published}", file=sys.stderr)
    sys.exit(1)


def ensure_remediation_workflows(
    client: "AoClient",
    project_id: str,
    sa_id: str,
    *,
    start_path: str,
    merged_path: str,
    build_path: str,  # unused; kept for call-site compat / chart env
    deploy_path: str,
    aap_org: str,
    aap_credential_id: str,
    aap_integration_id: str = "",
) -> None:
    del build_path  # ADR-039 — Build canvas retired into Merged
    retire_legacy_workflows(client, project_id)
    common = dict(
        aap_org=aap_org,
        aap_credential_id=aap_credential_id,
        aap_integration_id=aap_integration_id,
    )
    ensure_workflow(
        client,
        project_id,
        start_workflow_definition(sa_id, start_path, **common),
    )
    ensure_workflow(
        client,
        project_id,
        merged_workflow_definition(sa_id, merged_path, **common),
    )
    ensure_workflow(
        client,
        project_id,
        deploy_workflow_definition(sa_id, deploy_path, **common),
    )


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
    # Prefer AO_USERNAME — shell USERNAME is often the OS login (e.g. macOS).
    username = env("AO_USERNAME") or env("USERNAME", required=True)
    password = env("AO_PASSWORD") or env("PASSWORD", required=True)
    project_name = env("AO_PROJECT_NAME", f"lightwell-{guid}")
    start_path = env(
        "AO_START_WEBHOOK_PATH", f"lightwell-remediation-start-{guid}"
    )
    merged_path = env(
        "AO_MERGED_WEBHOOK_PATH", f"lightwell-remediation-merged-{guid}"
    )
    build_path = env(
        "AO_BUILD_WEBHOOK_PATH", f"lightwell-remediation-build-{guid}"
    )
    deploy_path = env(
        "AO_DEPLOY_WEBHOOK_PATH", f"lightwell-remediation-deploy-{guid}"
    )
    secret_name = env("AO_SECRET_NAME", "automation-orchestrator")
    secret_ns = env("AO_SECRET_NAMESPACE", required=True)
    aap_org = env("AAP_ORGANIZATION_NAME", f"user-{guid}")
    aap_admin_user = env("AAP_ADMIN_USERNAME", "admin")
    aap_admin_pass = env("AAP_ADMIN_PASSWORD", required=True)
    aap_base_url = env("AAP_BASE_URL", "")
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
    # project-user: SA can fire eda_trigger webhooks for this project.
    ensure_role_assignment(client, sa_id, "project-user", project_id)
    aap_cred_id = ensure_aap_credential(
        client,
        project_id,
        username=aap_admin_user,
        password=aap_admin_pass,
    )
    aap_integration_id = ""
    if aap_base_url:
        aap_integration_id = ensure_aap_integration(
            client,
            aap_base_url=aap_base_url,
            management_credential_id=aap_cred_id,
        )
    else:
        print(
            "WARNING: AAP_BASE_URL unset — skipping AAP integration create; "
            "aap_job_template nodes will fail until an integration exists.",
            file=sys.stderr,
        )
    ensure_remediation_workflows(
        client,
        project_id,
        sa_id,
        start_path=start_path,
        merged_path=merged_path,
        build_path=build_path,
        deploy_path=deploy_path,
        aap_org=aap_org,
        aap_credential_id=aap_cred_id,
        aap_integration_id=aap_integration_id,
    )
    write_k8s_secret(secret_ns, secret_name, client_id, client_secret, project_name)

    print(
        f"AO tenant ready: project={project_name} user={username} "
        f"start={start_path} merged={merged_path} (incl. build poll) "
        f"deploy={deploy_path} aap_org={aap_org}"
    )


if __name__ == "__main__":
    main()
