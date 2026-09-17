#!/usr/bin/env python3
"""
Idempotent AAP EDA bootstrap: project SCM sync, decision environment, rulebook activation.
Ported from lightwell-demo-collateral deploy-eda-complete.yml + deploy-aap-remediation.yml (activation refresh).
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        print(f"ERROR: missing env {name}", file=sys.stderr)
        sys.exit(1)
    return val or ""


def aap_request(
    method: str,
    path: str,
    user: str,
    password: str,
    base: str,
    body: dict | None = None,
    insecure: bool = True,
) -> tuple[int, Any]:
    url = f"{base.rstrip('/')}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    import base64

    req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode())
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


def first_result(data: Any) -> dict:
    if isinstance(data, dict) and "results" in data and data["results"]:
        return data["results"][0]
    return {}


def find_by_name(results: list, name: str) -> dict:
    for item in results or []:
        if item.get("name") == name:
            return item
    return {}


SDLC_JOB_TEMPLATES = [
    ("SDLC Query TPA", "playbooks/query-tpa.yml"),
    ("SDLC Trigger Impact Analyzer", "playbooks/trigger-impact-analyzer.yml"),
    ("SDLC Trigger MR Verifier", "playbooks/trigger-mr-verifier.yml"),
]


def ensure_controller_playbooks(
    user: str,
    password: str,
    base: str,
    controller_org_id: int,
    scm_url: str,
    project_name: str,
) -> tuple[int, int]:
    """Create Controller SCM project + localhost job templates for run_job_template actions."""
    code, invs = aap_request(
        "GET",
        "/api/controller/v2/inventories/?page_size=50",
        user,
        password,
        base,
    )
    inventory_id = 0
    if code == 200 and isinstance(invs, dict):
        for inv in invs.get("results", []):
            if inv.get("organization") == controller_org_id:
                inventory_id = int(inv["id"])
                break
        if not inventory_id:
            for inv in invs.get("results", []):
                if inv.get("name") == "Demo Inventory":
                    inventory_id = int(inv["id"])
                    break
        if not inventory_id and invs.get("results"):
            inventory_id = int(invs["results"][0]["id"])
    if not inventory_id:
        inventory_id = 1

    code, projects = aap_request(
        "GET",
        f"/api/controller/v2/projects/?search={urllib.parse.quote(project_name)}",
        user,
        password,
        base,
    )
    project = find_by_name(projects.get("results", []) if isinstance(projects, dict) else [], project_name)
    if not project:
        code, created = aap_request(
            "POST",
            "/api/controller/v2/projects/",
            user,
            password,
            base,
            {
                "name": project_name,
                "description": "SDLC remediation playbooks (same SCM as EDA project)",
                "organization": controller_org_id,
                "scm_type": "git",
                "scm_url": scm_url,
                "scm_clean": True,
                "scm_update_on_launch": True,
            },
        )
        if code in (200, 201) and isinstance(created, dict):
            project = created
        elif code == 400:
            code, projects = aap_request("GET", "/api/controller/v2/projects/", user, password, base)
            project = find_by_name(projects.get("results", []), project_name)
    project_id = int(project.get("id", 0))
    if not project_id:
        print("ERROR: Controller project missing", file=sys.stderr)
        sys.exit(1)
    aap_request("POST", f"/api/controller/v2/projects/{project_id}/update/", user, password, base)
    for attempt in range(30):
        code, st = aap_request("GET", f"/api/controller/v2/projects/{project_id}/", user, password, base)
        if code == 200 and isinstance(st, dict) and st.get("status") in ("successful", "failed"):
            break
        time.sleep(2)

    code, jts = aap_request("GET", "/api/controller/v2/job_templates/?page_size=200", user, password, base)
    existing = {j.get("name"): j for j in (jts.get("results", []) if isinstance(jts, dict) else [])}
    for jt_name, playbook in SDLC_JOB_TEMPLATES:
        if jt_name in existing:
            continue
        code, created = aap_request(
            "POST",
            "/api/controller/v2/job_templates/",
            user,
            password,
            base,
            {
                "name": jt_name,
                "description": f"SDLC remediation — {playbook}",
                "job_type": "run",
                "inventory": inventory_id,
                "project": project_id,
                "playbook": playbook,
                "organization": controller_org_id,
                "ask_variables_on_launch": True,
            },
        )
        if code not in (200, 201, 400):
            print(f"WARNING: job template {jt_name}: {code} {created}", file=sys.stderr)
    print(f"Controller project id={project_id}, inventory id={inventory_id}")
    return project_id, inventory_id


def ensure_eda_controller_credential(
    user: str,
    password: str,
    base: str,
    eda_org_id: int,
    cred_name: str,
) -> int:
    code, creds = aap_request("GET", "/api/eda/v1/eda-credentials/", user, password, base)
    cred = find_by_name(creds.get("results", []) if isinstance(creds, dict) else [], cred_name)
    if cred.get("id"):
        return int(cred["id"])
    controller_host = base.rstrip("/") + "/api/controller/"
    code, created = aap_request(
        "POST",
        "/api/eda/v1/eda-credentials/",
        user,
        password,
        base,
        {
            "name": cred_name,
            "credential_type_id": 4,
            "organization_id": eda_org_id,
            "inputs": {
                "host": controller_host,
                "username": user,
                "password": password,
                "verify_ssl": False,
            },
        },
    )
    if code in (200, 201) and isinstance(created, dict) and created.get("id"):
        return int(created["id"])
    if code == 400:
        code, creds = aap_request("GET", "/api/eda/v1/eda-credentials/", user, password, base)
        cred = find_by_name(creds.get("results", []), cred_name)
        return int(cred.get("id", 0))
    print(f"ERROR: EDA controller credential: {code} {created}", file=sys.stderr)
    sys.exit(1)


def build_extra_var_yaml() -> str:
    lines = [
        f"aap_organization_name: {env('EDA_ORGANIZATION_NAME') or env('AAP_ORGANIZATION_NAME', 'Default')}",
        f"tpa_url: {env('TPA_URL')}",
        f"keycloak_url: {env('KEYCLOAK_URL')}",
        f"keycloak_tpa_realm: {env('KEYCLOAK_TPA_REALM', 'trusted-profile-analyzer')}",
        f"tpa_oauth_client_id: {env('TPA_OAUTH_CLIENT_ID', 'trustify-ui')}",
        f"tpa_uploader_username: {env('TPA_UPLOADER_USERNAME')}",
        f"tpa_uploader_password: {env('TPA_UPLOADER_PASSWORD')}",
        f"tpa_sbom_label: {env('TPA_SBOM_LABEL')}",
        f"eda_webhook_url: {env('EDA_WEBHOOK_URL')}",
        f"gitlab_url: {env('GITLAB_URL')}",
        f"remediation_app_gitlab_path: {env('REMEDIATION_APP_GITLAB_PATH')}",
        f"opencode_base_url: {env('OPENCODE_BASE_URL')}",
        f"opencode_server_username: {env('OPENCODE_SERVER_USERNAME', 'opencode')}",
        f"opencode_server_password: {env('OPENCODE_SERVER_PASSWORD')}",
        f"validate_certs: {env('VALIDATE_CERTS', 'false')}",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    base = env("AAP_CONTROLLER_URL", required=True)
    user = env("AAP_USERNAME", required=True)
    password = env("AAP_PASSWORD", required=True)
    project_name = env("EDA_PROJECT_NAME", "SDLC OpenCode EDA")
    scm_url = env("EDA_PROJECT_SCM_URL", required=True)
    rulebook_name = env("EDA_RULEBOOK_NAME", "sdlc-remediation.yml")
    activation_name = env("EDA_ACTIVATION_NAME", "sdlc-remediation")
    de_name = env("EDA_DECISION_ENV_NAME", "SDLC Decision Environment")
    de_image = env("EDA_DECISION_ENV_IMAGE", "quay.io/ansible/ansible-rulebook:main")
    org_id = int(env("EDA_ORGANIZATION_ID", "0") or "0")
    org_name = env("EDA_ORGANIZATION_NAME", "")

    code, orgs = aap_request("GET", "/api/gateway/v1/organizations/", user, password, base)
    if org_id <= 0 and org_name and code == 200:
        results = orgs.get("results", []) if isinstance(orgs, dict) else []
        for o in results:
            if o.get("name") == org_name:
                org_id = int(o.get("id", 0))
                break
    if org_id <= 0 and code == 200:
        org_id = first_result(orgs).get("id", 1)
    print(f"Using organization_id={org_id}")

    code, projects = aap_request("GET", "/api/eda/v1/projects/", user, password, base)
    project = find_by_name(projects.get("results", []) if isinstance(projects, dict) else [], project_name)
    if not project:
        code, created = aap_request(
            "POST",
            "/api/eda/v1/projects/",
            user,
            password,
            base,
            {
                "name": project_name,
                "description": "SDLC remediation rulebooks and playbooks from sdlc-opencode git",
                "url": scm_url,
                "organization_id": org_id,
            },
        )
        if code not in (200, 201) and code != 400:
            print(f"ERROR creating EDA project: {code} {created}", file=sys.stderr)
            sys.exit(1)
        project = created if isinstance(created, dict) and created.get("id") else project
        if code == 400:
            code, projects = aap_request("GET", "/api/eda/v1/projects/", user, password, base)
            project = find_by_name(projects.get("results", []), project_name)
    project_id = project.get("id")
    if not project_id:
        print("ERROR: no EDA project id", file=sys.stderr)
        sys.exit(1)
    print(f"EDA project id={project_id}")

    aap_request("POST", f"/api/eda/v1/projects/{project_id}/sync/", user, password, base)
    for attempt in range(30):
        code, st = aap_request("GET", f"/api/eda/v1/projects/{project_id}/", user, password, base)
        if code == 200 and isinstance(st, dict) and st.get("import_state") == "completed":
            print("EDA project sync completed")
            break
        print(f"Waiting for project sync ({attempt + 1}/30)...")
        time.sleep(2)
    else:
        print("ERROR: EDA project sync did not complete", file=sys.stderr)
        sys.exit(1)

    code, des = aap_request("GET", "/api/eda/v1/decision-environments/", user, password, base)
    de = find_by_name(des.get("results", []) if isinstance(des, dict) else [], de_name)
    if not de:
        code, created = aap_request(
            "POST",
            "/api/eda/v1/decision-environments/",
            user,
            password,
            base,
            {
                "name": de_name,
                "description": "SDLC OpenCode remediation rulebooks",
                "image_url": de_image,
                "organization_id": org_id,
            },
        )
        if code in (200, 201):
            de = created
        elif code == 400:
            code, des = aap_request("GET", "/api/eda/v1/decision-environments/", user, password, base)
            de = find_by_name(des.get("results", []), de_name)
    de_id = de.get("id")
    if not de_id:
        print("ERROR: no decision environment id", file=sys.stderr)
        sys.exit(1)
    print(f"Decision environment id={de_id}")

    code, rbs = aap_request(
        "GET",
        f"/api/eda/v1/rulebooks/?project_id={project_id}",
        user,
        password,
        base,
    )
    rulebook = find_by_name(rbs.get("results", []) if isinstance(rbs, dict) else [], rulebook_name)
    if not rulebook:
        names = [r.get("name") for r in (rbs.get("results", []) if isinstance(rbs, dict) else [])]
        print(f"ERROR: rulebook '{rulebook_name}' not found in project. Available: {names}", file=sys.stderr)
        sys.exit(1)
    rulebook_id = rulebook["id"]
    print(f"Rulebook id={rulebook_id} ({rulebook_name})")

    controller_org_id = int(env("CONTROLLER_ORGANIZATION_ID", "0") or "0")
    if controller_org_id <= 0:
        corg_name = org_name or env("AAP_ORGANIZATION_NAME", "Default")
        code, corgs = aap_request("GET", "/api/controller/v2/organizations/", user, password, base)
        if code == 200 and isinstance(corgs, dict):
            for o in corgs.get("results", []):
                if o.get("name") == corg_name:
                    controller_org_id = int(o["id"])
                    break
    if controller_org_id <= 0:
        controller_org_id = 1
    ctrl_project_name = env("CONTROLLER_PROJECT_NAME", f"{project_name} Playbooks")
    ensure_controller_playbooks(user, password, base, controller_org_id, scm_url, ctrl_project_name)
    eda_cred_name = env("EDA_CONTROLLER_CREDENTIAL_NAME", "SDLC Controller")
    eda_cred_id = ensure_eda_controller_credential(user, password, base, org_id, eda_cred_name)
    print(f"EDA Controller credential id={eda_cred_id}")

    code, acts = aap_request("GET", "/api/eda/v1/activations/", user, password, base)
    activation = find_by_name(acts.get("results", []) if isinstance(acts, dict) else [], activation_name)
    extra_var = build_extra_var_yaml()

    if not activation:
        code, created = aap_request(
            "POST",
            "/api/eda/v1/activations/",
            user,
            password,
            base,
            {
                "name": activation_name,
                "description": "Nexus/GitLab webhooks → TPA → OpenCode (sdlc-remediation.yml)",
                "project_id": project_id,
                "rulebook_id": rulebook_id,
                "decision_environment_id": de_id,
                "restart_policy": "always",
                "is_enabled": False,
                "organization_id": org_id,
                "extra_var": extra_var,
            },
        )
        if code not in (200, 201):
            print(f"ERROR creating activation: {code} {created}", file=sys.stderr)
            sys.exit(1)
        activation = created
    activation_id = activation.get("id")
    if not activation_id:
        print("ERROR: no activation id", file=sys.stderr)
        sys.exit(1)

    aap_request("POST", f"/api/eda/v1/activations/{activation_id}/disable/", user, password, base)
    time.sleep(2)
    code, patched = aap_request(
        "PATCH",
        f"/api/eda/v1/activations/{activation_id}/",
        user,
        password,
        base,
        {
            "rulebook_id": rulebook_id,
            "extra_var": extra_var,
            "restart_count": 0,
            "eda_credentials": [eda_cred_id],
        },
    )
    if code != 200:
        print(f"WARNING: activation PATCH returned {code}: {patched}", file=sys.stderr)

    aap_request("POST", f"/api/eda/v1/activations/{activation_id}/enable/", user, password, base)
    for attempt in range(30):
        code, st = aap_request("GET", f"/api/eda/v1/activations/{activation_id}/", user, password, base)
        status = st.get("status") if isinstance(st, dict) else ""
        print(f"Activation status: {status}")
        if status == "running":
            print("EDA activation is running — rulebook ready.")
            print(f"Webhook listener (inventory): {env('EDA_WEBHOOK_URL')}")
            return
        if status == "failed":
            print(f"ERROR: activation failed: {st}", file=sys.stderr)
            sys.exit(1)
        time.sleep(3)
    print("ERROR: activation did not reach running state", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
