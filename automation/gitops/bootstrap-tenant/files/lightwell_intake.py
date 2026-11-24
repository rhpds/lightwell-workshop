"""One Lightwell rebuild: parent incident, blast radius, Renovate for platform apps.

The EventListener names the PipelineRun from pipeline_run_name(). A second
event for the same artifact and version collides with that name and does not
start another run. This module is the body of that single run.
"""

from __future__ import annotations

import base64
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


def pipeline_run_name(artifact: str, version: str) -> str:
    """DNS-1123 name. Keep in step with the CEL overlay on the EventListener."""
    art = re.sub(r"[^a-z0-9-]", "-", artifact.lower()).strip("-")[:22].strip("-")
    ver = re.sub(r"[^a-z0-9-]", "-", version.lower()).strip("-")[:30].strip("-")
    name = f"lw-{art}-{ver}".strip("-")
    return name[:63].strip("-")


def event_key(guid: str, group: str, artifact: str, version: str) -> str:
    return f"{guid}:{group}:{artifact}:{version}"


def accept_event(version: str, key: str, existing_keys: set[str]) -> bool:
    if not version or "rhlw-" not in version:
        return False
    return key not in existing_keys


def purl_needle(group: str, artifact: str) -> str:
    return f"pkg:maven/{group}/{artifact}"


def affected_from_packages(packages_by_app: dict[str, str], group: str, artifact: str) -> list[str]:
    """packages_by_app maps an app name to the raw packages response body."""
    needle = purl_needle(group, artifact)
    return [app for app, body in packages_by_app.items() if needle in body]


@dataclass
class AppPolicy:
    name: str
    policy: dict | None
    valid: bool


@dataclass
class IntakePlan:
    ok: bool
    comment: str
    platform: list[AppPolicy] = field(default_factory=list)
    skipped: list[AppPolicy] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    error: str = ""


def plan_apps(found: list[AppPolicy]) -> IntakePlan:
    if not found:
        return IntakePlan(ok=False, comment="No applications in Trusted Profile Analyzer.", error="empty blast radius")
    platform: list[AppPolicy] = []
    skipped: list[AppPolicy] = []
    invalid: list[str] = []
    for app in found:
        if not app.valid or not app.policy:
            invalid.append(app.name)
            continue
        owner = app.policy.get("remediation_owner")
        if owner == "ao":
            platform.append(app)
        elif owner == "renovate":
            skipped.append(app)
        else:
            invalid.append(app.name)
    lines = ["Platform applications:"]
    if platform:
        for app in platform:
            lines.append(f"- {app.name} approval={app.policy.get('approval', '')}")
    else:
        lines.append("- (none)")
    if skipped:
        lines.append("Skipped Renovate-owned applications:")
        for app in skipped:
            lines.append(f"- {app.name}")
    if invalid:
        lines.append("Policy missing or invalid:")
        for name in invalid:
            lines.append(f"- {name}")
    ok = bool(platform) or (bool(skipped) and not invalid and not platform)
    # A renovate-only hit is a successful skip. Invalid-only, or a mix that
    # produced no platform app and no clean skip, fails the run.
    if invalid and not platform:
        ok = False
    if not platform and not skipped:
        ok = False
    error = "" if ok else "no platform application to remediate"
    return IntakePlan(ok=ok, comment="\n".join(lines), platform=platform, skipped=skipped, invalid=invalid, error=error)


def _pr_body(risk_class: str, approval: str) -> str:
    """Note Renovate renders once per upgrade.

    prBodyTemplate only inserts named sections (header, notes, footer). The
    upgrade fields are available in prBodyNotes, which is that notes section.
    The risk class is already known from the application policy, so it is
    written literally.
    """
    risk = risk_class or "NONE"
    recorded = approval or "unspecified"
    return (
        "Lightwell rebuild of {{{depName}}} from {{{currentVersion}}} to {{{newVersion}}}.\n\n"
        "Renovate changed the dependency version. The pipeline measures that change. "
        "A person merges the request.\n\n"
        "<!-- lw:validation:start -->\n"
        "| Check | Status | Details |\n"
        "|---|---|---|\n"
        f"| Acme Inc. Risk Class | {risk} | Recorded from .lightwell/policy.json ({recorded}). |\n"
        "<!-- lw:validation:end -->\n\n"
        "<!-- lw:action:start -->\n"
        "<!-- lw:action:end -->\n\n"
        "```json\n"
        '{"artifact_id": "{{{depName}}}", "new_version": "{{{newVersion}}}", '
        '"old_version": "{{{currentVersion}}}"}\n'
        "```\n"
    )


def renovate_job(
    *,
    app: str,
    gitlab_group: str,
    namespace: str,
    gitlab_endpoint: str,
    nexus_host: str,
    nexus_password: str,
    gav: str,
    risk_class: str = "",
    approval: str = "",
) -> dict:
    """RenovateJob that does not extend the upstream preset's registry URL."""
    config = {
        "onboarding": False,
        "requireConfig": "optional",
        "branchConcurrentLimit": 0,
        "prConcurrentLimit": 0,
        "prHourlyLimit": 0,
        "commitMessagePrefix": "[Lightwell]",
        "commitMessageExtra": "({{{newVersion}}})",
        "hostRules": [
            {
                "matchHost": nexus_host,
                "hostType": "maven",
                "username": "admin",
                "password": nexus_password,
            }
        ],
        "customManagers": [
            {
                "customType": "regex",
                "managerFilePatterns": ["/(^|/)pom\\.xml$/"],
                "matchStringsStrategy": "any",
                "matchStrings": [
                    "<groupId>(?<groupId>[^<]+)</groupId>\\s*<artifactId>(?<artifactId>[^<]+)</artifactId>\\s*<version>(?<currentValue>[^<${}]+)</version>"
                ],
                "depNameTemplate": "{{{groupId}}}:{{{artifactId}}}",
                "datasourceTemplate": "maven",
                "registryUrlTemplate": f"https://{nexus_host}/repository/maven-public",
                "versioningTemplate": "regex:^(?<compatibility>.*?)([.-]rhlw-(?<major>\\d+)(\\.n(?<minor>\\d+))?)?$",
            }
        ],
        "packageRules": [{"matchPackageNames": ["com.acme.*:*"], "enabled": False}],
        "dockerfile": {"enabled": False},
        "github-actions": {"enabled": False},
        "prBodyNotes": [_pr_body(risk_class, approval)],
        "prBodyTemplate": "{{{notes}}}",
    }
    encoded = json.dumps(config)
    if "github>lightwell" in encoded or "packages.redhat.com" in encoded:
        raise RuntimeError("Renovate config still points at the upstream registry")
    slug = re.sub(r"[^a-z0-9-]", "-", app.lower()).strip("-")[:40]
    return {
        "apiVersion": "renovate-operator.mogenius.com/v1alpha1",
        "kind": "RenovateJob",
        "metadata": {
            "name": f"lw-{slug}",
            "namespace": namespace,
            "annotations": {"lightwell.intake/gav": gav},
        },
        "spec": {
            "schedule": "*/5 * * * *",
            "parallelism": 1,
            "secretRef": "renovate-token",
            "serviceAccount": {"name": "renovate-runner"},
            "provider": {"name": "gitlab", "endpoint": gitlab_endpoint},
            "discoveryFilters": [f"{gitlab_group}/{app}"],
            "image": "ghcr.io/renovatebot/renovate:44.145.1",
            "renovateConfig": {"fileName": "config.json", "inline": encoded},
        },
    }


def _request(method: str, url: str, body: dict | None = None, headers: dict | None = None, form: str | None = None):
    data = None
    hdrs = dict(headers or {})
    if form is not None:
        data = form.encode()
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def gitlab_policy(gitlab_url: str, token: str, project_path: str) -> tuple[dict | None, bool]:
    enc = urllib.parse.quote(project_path, safe="")
    file_enc = urllib.parse.quote(".lightwell/policy.json", safe="")
    url = f"{gitlab_url.rstrip('/')}/api/v4/projects/{enc}/repository/files/{file_enc}/raw?ref=main"
    status, raw = _request("GET", url, headers={"PRIVATE-TOKEN": token})
    if status == 404:
        return None, False
    if status != 200:
        return None, False
    try:
        return json.loads(raw), True
    except json.JSONDecodeError:
        return None, False


def tpa_access_token(token_url: str, client_id: str, client_secret: str) -> str:
    form = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    )
    status, raw = _request("POST", token_url, form=form)
    if status != 200:
        raise RuntimeError(f"TPA token request failed: HTTP {status}")
    token = json.loads(raw).get("access_token") or ""
    if not token:
        raise RuntimeError("TPA token response had no access_token")
    return token


def tpa_affected(tpa_url: str, token: str, group: str, artifact: str, app_names: list[str]) -> list[str]:
    headers = {"Authorization": f"Bearer {token}"}
    bodies: dict[str, str] = {}
    for app in app_names:
        query = urllib.parse.urlencode({"q": f"name={app}", "sort": "ingested:desc", "limit": "1"})
        status, raw = _request("GET", f"{tpa_url.rstrip('/')}/api/v3/sbom?{query}", headers=headers)
        if status != 200:
            continue
        payload = json.loads(raw)
        items = payload.get("items") or payload.get("result") or []
        if isinstance(items, dict):
            items = items.get("items") or []
        if not items:
            continue
        sbom_id = items[0].get("id") or items[0].get("sbom_id")
        if not sbom_id:
            continue
        pkg_q = urllib.parse.urlencode({"q": artifact})
        pstatus, praw = _request(
            "GET",
            f"{tpa_url.rstrip('/')}/api/v3/sbom/{sbom_id}/packages?{pkg_q}",
            headers=headers,
        )
        if pstatus == 200:
            bodies[app] = praw
    return affected_from_packages(bodies, group, artifact)


def snow_create(snow_url: str, payload: dict) -> str:
    status, raw = _request("POST", f"{snow_url.rstrip('/')}/api/v1/incidents", payload)
    if status not in (200, 201):
        raise RuntimeError(f"snow create failed: HTTP {status} {raw}")
    return json.loads(raw)["result"]["number"]


def snow_comment(snow_url: str, number: str, text: str) -> None:
    status, raw = _request(
        "POST",
        f"{snow_url.rstrip('/')}/api/v1/incidents/{number}/comments",
        {"comment": text, "created_by": "lightwell-intake"},
    )
    if status not in (200, 201):
        raise RuntimeError(f"snow comment failed: HTTP {status} {raw}")


def _kube(method: str, url: str, body: dict | None = None) -> tuple[int, str]:
    token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    ca = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    with open(token_path, encoding="utf-8") as fh:
        token = fh.read().strip()
    ctx = ssl.create_default_context(cafile=ca) if os.path.exists(ca) else ssl._create_unverified_context()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def kube_secret(namespace: str, name: str, key: str) -> str:
    base = os.environ.get("KUBERNETES_API", "https://kubernetes.default.svc")
    status, raw = _kube("GET", f"{base}/api/v1/namespaces/{namespace}/secrets/{name}")
    if status != 200:
        raise RuntimeError(f"secret {namespace}/{name} failed: HTTP {status}")
    encoded = json.loads(raw)["data"][key]
    return base64.b64decode(encoded).decode()


def kube_apply_renovate_job(manifest: dict) -> None:
    ns = manifest["metadata"]["namespace"]
    name = manifest["metadata"]["name"]
    base = os.environ.get("KUBERNETES_API", "https://kubernetes.default.svc")
    root = f"{base}/apis/renovate-operator.mogenius.com/v1alpha1/namespaces/{ns}/renovatejobs"
    status, existing = _kube("GET", f"{root}/{name}")
    method, url = ("POST", root)
    if status == 200:
        manifest.setdefault("metadata", {})["resourceVersion"] = json.loads(existing)["metadata"]["resourceVersion"]
        method, url = "PUT", f"{root}/{name}"
    applied, detail = _kube(method, url, manifest)
    if applied not in (200, 201):
        raise RuntimeError(f"RenovateJob apply failed: HTTP {applied} {detail}")


@dataclass
class IntakeResult:
    ok: bool
    parent: str
    children: dict[str, str]
    jobs: list[dict]
    comment: str
    error: str = ""


def run_intake(
    *,
    guid: str,
    group: str,
    artifact: str,
    version: str,
    app_names: list[str],
    gitlab_group: str,
    gitlab_url: str,
    gitlab_token: str,
    tpa_url: str,
    tpa_token: str,
    snow_url: str,
    renovate_namespace: str,
    gitlab_endpoint: str,
    nexus_host: str,
    nexus_password: str,
) -> IntakeResult:
    gav = f"{group}:{artifact}:{version}"
    parent = snow_create(
        snow_url,
        {
            "short_description": f"[Lightwell] {gav}",
            "description": f"Lightwell rebuild {gav} for tenant {guid}",
            "caller_id": "lightwell-intake",
            "guid": guid,
            "cmdb_ci": artifact,
        },
    )
    affected = tpa_affected(tpa_url, tpa_token, group, artifact, app_names)
    found: list[AppPolicy] = []
    for app in affected:
        policy, valid = gitlab_policy(gitlab_url, gitlab_token, f"{gitlab_group}/{app}")
        found.append(AppPolicy(app, policy, valid))
    decision = plan_apps(found)
    snow_comment(snow_url, parent, decision.comment)
    if not decision.ok:
        return IntakeResult(False, parent, {}, [], decision.comment, decision.error)
    children: dict[str, str] = {}
    jobs: list[dict] = []
    for app in decision.platform:
        number = snow_create(
            snow_url,
            {
                "short_description": f"[Lightwell] {app.name} {gav}",
                "description": f"Remediate {app.name} for {gav}",
                "caller_id": "lightwell-intake",
                "guid": guid,
                "cmdb_ci": app.name,
                "parent_incident": parent,
            },
        )
        children[app.name] = number
        jobs.append(
            renovate_job(
                app=app.name,
                gitlab_group=gitlab_group,
                namespace=renovate_namespace,
                gitlab_endpoint=gitlab_endpoint,
                nexus_host=nexus_host,
                nexus_password=nexus_password,
                gav=gav,
                risk_class=str((app.policy or {}).get("riskClass") or ""),
                approval=str((app.policy or {}).get("approval") or ""),
            )
        )
    return IntakeResult(True, parent, children, jobs, decision.comment)


def main() -> None:
    version = os.environ["VERSION"]
    guid = os.environ["GUID"]
    group = os.environ["GROUP"]
    artifact = os.environ["ARTIFACT"]
    key = event_key(guid, group, artifact, version)
    if not accept_event(version, key, set()):
        print(f"ignore event {key}")
        return
    token = tpa_access_token(
        os.environ["KC_TOKEN_URL"],
        os.environ["TPA_CLIENT_ID"],
        os.environ["TPA_CLIENT_SECRET"],
    )
    result = run_intake(
        guid=guid,
        group=group,
        artifact=artifact,
        version=version,
        app_names=[a for a in os.environ["APP_NAMES"].split(",") if a],
        gitlab_group=os.environ["GITLAB_GROUP"],
        gitlab_url=os.environ["GITLAB_URL"],
        gitlab_token=os.environ["GITLAB_TOKEN"],
        tpa_url=os.environ["TPA_URL"],
        tpa_token=token,
        snow_url=os.environ["SNOW_URL"],
        renovate_namespace=os.environ["RENOVATE_NAMESPACE"],
        gitlab_endpoint=os.environ["GITLAB_ENDPOINT"],
        nexus_host=os.environ["NEXUS_HOST"],
        nexus_password=os.environ.get("NEXUS_ADMIN_PASSWORD")
        or kube_secret(os.environ["NEXUS_SECRET_NAMESPACE"], "nexus-admin-secret", "password"),
    )
    for job in result.jobs:
        kube_apply_renovate_job(job)
        print(f"RenovateJob {job['metadata']['namespace']}/{job['metadata']['name']}")
    print(result.comment)
    if not result.ok:
        print(result.error, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
