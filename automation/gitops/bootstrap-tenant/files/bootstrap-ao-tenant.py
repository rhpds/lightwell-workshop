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
  5. Published ``Lightwell Remediation`` workflow — SNOW → Query TPA →
     classify → for-each (Impact → Verifier → auto merge **or**
     await GitLab student merge → await_build → await_deploy) → finalize;
     EDA bridge SA gets project-user so it can PATCH Approval gates
  6. Writes client_id / client_secret into a Kubernetes Secret for EDA bootstrap

Requires env:
  AO_BASE_URL, AO_ADMIN_USERNAME, AO_ADMIN_PASSWORD, GUID, USERNAME, PASSWORD
  AAP_ADMIN_USERNAME, AAP_ADMIN_PASSWORD (Controller API for aap_job_template nodes)
Optional:
  AO_PROJECT_NAME (default lightwell-{guid})
  AO_START_WEBHOOK_PATH / AO_RESUME_WEBHOOK_PATH
  AAP_ORGANIZATION_NAME (default user-{guid})
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
JT_SNOW_CHILDREN = "SDLC SNOW Create Children"
JT_SNOW_ITER = "SDLC SNOW Iteration Comment"
JT_SNOW_FINALIZE = "SDLC SNOW Finalize"
JT_MERGE_MR = "SDLC Merge GitLab MR"
AAP_INTEGRATION_NAME = "AAP Lightwell"
# CI/CD Approval gates (EDA signals via PATCH /approvals — not duration Wait).
CICD_DECISION_WINDOW_SEC = 1800  # 30m demo deadline; fallback reject


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


def remediation_workflow_definition(
    sa_id: str,
    start_path: str,
    resume_path: str,
    *,
    aap_org: str,
    aap_credential_id: str,
    remediation_app_git_url: str = "",
    aap_integration_id: str = "",
) -> dict:
    """Multi-app remediation: SNOW → TPA → classify → for-each → finalize.

    In-run Verifier + if(auto_approve)/else Approval + merge is the only path. GitLab MR-open
    → Resume → mr_verifier_legacy was removed — it dual-fired Verifier and raced
    the in-loop agent.
    """
    # Prefer values baked at publish time from tenant-integration. EDA
    # run_job_template job_args historically omitted snow_*/gitlab_token/
    # tpa_oauth_client_secret even when the activation had them, so relying
    # solely on ${trigger.*} left Create SNOW (and later nodes) empty.
    snow_url = env("SNOW_URL", "")
    snow_svc_url = env("SNOW_SVC_URL", "")
    gitlab_token = env("GITLAB_TOKEN", "")
    tpa_oauth_client_secret = env("TPA_OAUTH_CLIENT_SECRET", "")

    trigger_common = {
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
        "gitlab_token": (
            gitlab_token if gitlab_token else "${trigger.gitlab_token}"
        ),
        "remediation_app_gitlab_path": "${trigger.remediation_app_gitlab_path}",
        "eda_webhook_url": "${trigger.eda_webhook_url}",
        "blast_radius_mode": "${trigger.blast_radius_mode}",
        "opencode_base_url": "${trigger.opencode_base_url}",
        "opencode_server_username": "${trigger.opencode_server_username}",
        "opencode_server_password": "${trigger.opencode_server_password}",
        "aap_organization_name": "${trigger.aap_organization_name}",
        "guid": "${trigger.guid}",
        "snow_url": snow_url if snow_url else "${trigger.snow_url}",
        "snow_svc_url": snow_svc_url if snow_svc_url else "${trigger.snow_svc_url}",
    }
    snow_create_vars = {
        **trigger_common,
    }
    query_vars = {
        **trigger_common,
    }
    classify_vars = {
        **trigger_common,
        "affected_repos": "${query_tpa.artifacts.affected_repos}",
        "package_info": "${query_tpa.artifacts.package_info}",
        "blast_radius": "${query_tpa.artifacts.blast_radius}",
        "snow_incident": "${snow_create.artifacts.parent_incident}",
        "parent_incident": "${snow_create.artifacts.parent_incident}",
    }
    # Use baked snow_* (same as trigger_common), not bare ${trigger.snow_*} —
    # EDA Start Orchestrator often omits snow_url from the AO payload, which
    # left Create SNOW OK (trigger_common) but classify/iter/finalize comments
    # failing with empty snow_base (seen on cng2l jobs 38/48).
    # Parent INC from snow_create; children from snow_children (after classify).
    parent_inc = "${snow_create.artifacts.parent_incident}"
    classify_comment_vars = {
        "snow_url": trigger_common["snow_url"],
        "snow_svc_url": trigger_common["snow_svc_url"],
        "snow_incident": parent_inc,
        "snow_comment_body": "${classify.artifacts.snow_comment_body}",
        "guid": "${trigger.guid}",
    }
    snow_children_vars = {
        **trigger_common,
        "parent_incident": parent_inc,
        "snow_incident": parent_inc,
        "ao_apps": "${classify.artifacts.ao_apps}",
        "renovate_skips": "${classify.artifacts.renovate_skips}",
        "package_info": "${classify.artifacts.package_info}",
        "cve_id": "${trigger.cve_id}",
    }
    # Loop body: one AO-owned app from snow_children.ao_apps (includes child_incident).
    # Inside a for_each body, `loop` is already the current loop context — use
    # ${loop.item}, not ${loop.<loop_id>.item} (that double-scopes to
    # loop.apps_loop.apps_loop.item and fails expression resolve).
    impact_vars = {
        **trigger_common,
        "package_info": "${snow_children.artifacts.package_info}",
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
    merge_vars = {
        **trigger_common,
        "merge_request_iid": "${verifier.artifacts.merge_request_iid}",
        "project_id": "${verifier.artifacts.project_id}",
        "gitlab_path": "${verifier.artifacts.gitlab_path}",
        "snow_incident": "${loop.item.child_incident}",
        "child_incident": "${loop.item.child_incident}",
        "parent_incident": parent_inc,
    }
    iter_comment_base = {
        "snow_url": trigger_common["snow_url"],
        "snow_svc_url": trigger_common["snow_svc_url"],
        "snow_incident": "${loop.item.child_incident}",
        "child_incident": "${loop.item.child_incident}",
        "parent_incident": parent_inc,
        "gitlab_path": "${verifier.artifacts.gitlab_path}",
        "approval": "${verifier.artifacts.approval}",
        "merge_request_iid": "${verifier.artifacts.merge_request_iid}",
        "verifier_status": "${verifier.artifacts.verifier_status}",
        "guid": "${trigger.guid}",
    }
    # Impact already_current never reaches Verifier — comment from impact arts.
    iter_comment_already = {
        "snow_url": trigger_common["snow_url"],
        "snow_svc_url": trigger_common["snow_svc_url"],
        "snow_incident": "${loop.item.child_incident}",
        "child_incident": "${loop.item.child_incident}",
        "parent_incident": parent_inc,
        "gitlab_path": "${impact.artifacts.gitlab_path}",
        "approval": "${impact.artifacts.approval}",
        "merge_request_iid": "${impact.artifacts.merge_request_iid}",
        "verifier_status": "n/a",
        "guid": "${trigger.guid}",
        "iteration_outcome": "already_current",
    }
    finalize_vars = {
        "snow_url": trigger_common["snow_url"],
        "snow_svc_url": trigger_common["snow_svc_url"],
        "parent_incident": parent_inc,
        "snow_incident": parent_inc,
        "guid": "${trigger.guid}",
        "snow_comment_body": (
            "Lightwell AO multi-app remediation finished "
            "(guid=${trigger.guid}). See child incidents for per-app outcomes."
        ),
    }
    _ = (remediation_app_git_url, resume_path)  # resume_path unused; kept for call-site compat

    return {
        "name": "Lightwell Remediation",
        "description": (
            "Nexus→EDA→AO: parent SNOW → Query TPA → classify → child SNOW → "
            "for-each (Impact → Verifier → auto_approve: AO merge | "
            "needs_approval: student merges in GitLab → await_build → "
            "await_deploy) → parent SNOW finalize"
        ),
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
        ],
        "nodes": [
            _aap_jt_node(
                "snow_create",
                "Create parent SNOW incident",
                JT_SNOW_CREATE,
                aap_org,
                aap_credential_id,
                snow_create_vars,
                integration_id=aap_integration_id,
            ),
            _aap_jt_node(
                "query_tpa",
                "Query TPA",
                JT_QUERY_TPA,
                aap_org,
                aap_credential_id,
                query_vars,
                integration_id=aap_integration_id,
            ),
            # No condition gate here: a failed aap_job_template already stops the
            # run. A condition on ${query_tpa.job_status} was dead-ending the
            # canvas (field not populated as expected → false → no classify).
            _aap_jt_node(
                "classify",
                "Classify affected apps",
                JT_CLASSIFY,
                aap_org,
                aap_credential_id,
                classify_vars,
                integration_id=aap_integration_id,
            ),
            _aap_jt_node(
                "snow_classify_comment",
                "SNOW classify comment (parent)",
                JT_SNOW_COMMENT,
                aap_org,
                aap_credential_id,
                classify_comment_vars,
                integration_id=aap_integration_id,
            ),
            _aap_jt_node(
                "snow_children",
                "Create child SNOW incidents",
                JT_SNOW_CHILDREN,
                aap_org,
                aap_credential_id,
                snow_children_vars,
                integration_id=aap_integration_id,
            ),
            {
                "id": "apps_loop",
                "name": "Remediate AO apps",
                "type": "loop",
                # items must be an expression string (not a literal list).
                # Body nodes hang off from_port=iterate; do NOT edge back to the
                # loop (API treats that as an illegal cycle). AO returns to the
                # loop when the iterate branch ends, then follows complete.
                # Use snow_children.ao_apps so each item carries child_incident.
                "parameters": {
                    "type": "for_each",
                    "items": "${snow_children.artifacts.ao_apps}",
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
                # OpenCode / pom already on fix_version → skip Verifier+merge.
                # Impact set_stats iteration_outcome=already_current|mr_opened.
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
                    # Prefer set_stats from the Verifier playbook — job_status
                    # is not reliably exposed on aap_job_template node outputs.
                    # AO treats bare `true` as a step name; compare the string
                    # iteration_outcome instead of a boolean literal.
                    "condition": '${verifier.artifacts.iteration_outcome} == "verifier_pass"',
                },
            },
            {
                # Binary if/else — do NOT use switch with default_port equal to a
                # case port (AO: "Case port 'auto_approve' conflicts with
                # default_port"). Value must not be bare "auto" (Ansible/AO
                # reserved); policy artifact is auto_approve | needs_approval.
                "id": "approval_auto",
                "name": "Auto-approve?",
                "type": "condition",
                "parameters": {
                    "condition": (
                        '${verifier.artifacts.approval} == "auto_approve"'
                    ),
                },
            },
            _aap_jt_node(
                "merge_auto",
                "Merge MR (auto)",
                JT_MERGE_MR,
                aap_org,
                aap_credential_id,
                merge_vars,
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            {
                # needs_approval: student merges in GitLab UI. EDA MR-merged
                # webhook signals this gate (AO does NOT merge). Not ADR-025
                # MR-open Resume — merge only, then CI gates.
                "id": "await_gitlab_merge",
                "name": "Await GitLab merge (student)",
                "type": "approval",
                "parameters": {
                    "prompt": (
                        "Merge the verified remediation MR in GitLab for "
                        "${verifier.artifacts.gitlab_path} "
                        "(!${verifier.artifacts.merge_request_iid}), then EDA "
                        "will continue (guid=${trigger.guid}). "
                        "AO will not merge this MR."
                    ),
                    "decision_window": 86400,
                    "fallback_decision": "reject",
                },
                "settings": {"continue_on_failure": True},
            },
            {
                # Park until EDA signals PipelineRun terminal (not duration Wait).
                "id": "await_build",
                "name": "Await CI build",
                "type": "approval",
                "parameters": {
                    "prompt": (
                        "CI/CD build gate: awaiting PipelineRun for "
                        "${verifier.artifacts.gitlab_path} "
                        "(guid=${trigger.guid}). EDA will approve/reject."
                    ),
                    "decision_window": CICD_DECISION_WINDOW_SEC,
                    "fallback_decision": "reject",
                },
                "settings": {"continue_on_failure": True},
            },
            {
                # Park until EDA signals Argo Synced+Healthy (or failure).
                "id": "await_deploy",
                "name": "Await deploy Healthy",
                "type": "approval",
                "parameters": {
                    "prompt": (
                        "CI/CD deploy gate: awaiting Argo Synced+Healthy for "
                        "${verifier.artifacts.gitlab_path} "
                        "(guid=${trigger.guid}). EDA will approve/reject."
                    ),
                    "decision_window": CICD_DECISION_WINDOW_SEC,
                    "fallback_decision": "reject",
                },
                "settings": {"continue_on_failure": True},
            },
            _aap_jt_node(
                "snow_iter_ok",
                "SNOW iteration (deployed)",
                JT_SNOW_ITER,
                aap_org,
                aap_credential_id,
                {**iter_comment_base, "iteration_outcome": "deployed"},
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "snow_iter_build_fail",
                "SNOW iteration (build failed / timeout)",
                JT_SNOW_ITER,
                aap_org,
                aap_credential_id,
                {
                    **iter_comment_base,
                    "iteration_outcome": "build_failed",
                },
                integration_id=aap_integration_id,
                continue_on_failure=True,
            ),
            _aap_jt_node(
                "snow_iter_deploy_fail",
                "SNOW iteration (deploy failed / timeout)",
                JT_SNOW_ITER,
                aap_org,
                aap_credential_id,
                {
                    **iter_comment_base,
                    "iteration_outcome": "deploy_failed",
                },
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
                "snow_iter_reject",
                "SNOW iteration (merge not completed)",
                JT_SNOW_ITER,
                aap_org,
                aap_credential_id,
                {**iter_comment_base, "iteration_outcome": "merge_abandoned"},
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
            {"from": "start_trigger", "to": "snow_create"},
            {"from": "snow_create", "to": "query_tpa"},
            {"from": "query_tpa", "to": "classify"},
            {"from": "classify", "to": "snow_classify_comment"},
            {"from": "snow_classify_comment", "to": "snow_children"},
            {"from": "snow_children", "to": "apps_loop"},
            # for-each body
            {"from": "apps_loop", "to": "impact", "from_port": "iterate"},
            {"from": "impact", "to": "impact_already"},
            {
                "from": "impact_already",
                "to": "snow_iter_already",
                "from_port": "true",
            },
            {"from": "impact_already", "to": "verifier", "from_port": "false"},
            {"from": "verifier", "to": "verifier_ok"},
            {"from": "verifier_ok", "to": "approval_auto", "from_port": "true"},
            {"from": "verifier_ok", "to": "snow_iter_fail", "from_port": "false"},
            {"from": "approval_auto", "to": "merge_auto", "from_port": "true"},
            {
                "from": "approval_auto",
                "to": "await_gitlab_merge",
                "from_port": "false",
            },
            {"from": "merge_auto", "to": "await_build"},
            {
                "from": "await_gitlab_merge",
                "to": "await_build",
                "from_port": "approved",
            },
            {
                "from": "await_gitlab_merge",
                "to": "snow_iter_reject",
                "from_port": "rejected",
            },
            {"from": "await_build", "to": "await_deploy", "from_port": "approved"},
            {
                "from": "await_build",
                "to": "snow_iter_build_fail",
                "from_port": "rejected",
            },
            {"from": "await_deploy", "to": "snow_iter_ok", "from_port": "approved"},
            {
                "from": "await_deploy",
                "to": "snow_iter_deploy_fail",
                "from_port": "rejected",
            },
            # Iteration ends at snow_iter_* (no edge back to apps_loop — illegal cycle).
            {"from": "apps_loop", "to": "snow_finalize", "from_port": "complete"},
        ],
    }


def ensure_workflow(
    client: AoClient,
    project_id: str,
    sa_id: str,
    start_path: str,
    resume_path: str,
    *,
    aap_org: str,
    aap_credential_id: str,
    remediation_app_git_url: str = "",
    aap_integration_id: str = "",
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
    defn = remediation_workflow_definition(
        sa_id,
        start_path,
        resume_path,
        aap_org=aap_org,
        aap_credential_id=aap_credential_id,
        remediation_app_git_url=remediation_app_git_url,
        aap_integration_id=aap_integration_id,
    )
    code, validated = client.request(
        "POST", "/api/v1/workflows/validate", {"workflow_definition": defn}
    )
    result = validated if isinstance(validated, dict) else {}
    if code != 200 or result.get("is_valid") is False:
        print(f"ERROR: workflow definition invalid: {code} {validated}", file=sys.stderr)
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

    ver = detail.get("current_version") or 1
    published_ver = detail.get("published_version_number")
    # Always publish after PATCH so a new draft version becomes live.
    # Skip only when this exact version is already the published enabled one
    # and we did not just create/patch (caller always patches when existing).
    code, published = client.request(
        "POST",
        f"/api/v1/workflows/{wf_id}/versions/{ver}/publish",
        {
            "publish_name": f"tenant-{start_path}",
            "change_description": "Per-tenant Lightwell remediation (AAP JT canvas)",
        },
    )
    if code in (200, 201):
        print(f"AO workflow published (version {ver})")
        return wf_id
    # Idempotent: already published at this version
    if published_ver == ver and detail.get("is_enabled"):
        print(f"AO workflow already published (version {ver}): {published}")
        return wf_id
    print(f"ERROR: publish workflow failed: {code} {published}", file=sys.stderr)
    sys.exit(1)


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
    resume_path = env(
        "AO_RESUME_WEBHOOK_PATH", f"lightwell-remediation-resume-{guid}"
    )
    secret_name = env("AO_SECRET_NAME", "automation-orchestrator")
    secret_ns = env("AO_SECRET_NAMESPACE", required=True)
    aap_org = env("AAP_ORGANIZATION_NAME", f"user-{guid}")
    aap_admin_user = env("AAP_ADMIN_USERNAME", "admin")
    aap_admin_pass = env("AAP_ADMIN_PASSWORD", required=True)
    remediation_app_git_url = env("REMEDIATION_APP_GIT_URL", "")
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
    # CI/CD gates are Approval nodes decided by EDA via the SA (PATCH /approvals).
    # Without project-user the SA sees zero approvals and cannot signal gates.
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
    ensure_workflow(
        client,
        project_id,
        sa_id,
        start_path,
        resume_path,
        aap_org=aap_org,
        aap_credential_id=aap_cred_id,
        remediation_app_git_url=remediation_app_git_url,
        aap_integration_id=aap_integration_id,
    )
    write_k8s_secret(secret_ns, secret_name, client_id, client_secret, project_name)

    print(
        f"AO tenant ready: project={project_name} user={username} "
        f"start_path={start_path} resume_path={resume_path} "
        f"aap_org={aap_org}"
    )


if __name__ == "__main__":
    main()
