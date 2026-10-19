#!/usr/bin/env python3
"""Watch Acme Argo Application (and optionally PipelineRuns); POST to EDA.

Deploy: emits argo_app_health for AO Deploy (ADR-036).

Build: PipelineRun→EDA→AO Build was retired (ADR-039). Merged AO polls PaC
commit status instead. scan_pipelineruns still primes annotations so a future
re-enable does not storm EDA; POSTs are off unless POST_BUILD_EVENTS=true.
"""
from __future__ import annotations

import base64
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GUID = os.environ["GUID"]
EDA_URL = os.environ["EDA_URL"].rstrip("/") + "/"
BUILD_NS = os.environ.get("BUILD_NAMESPACE", f"build-{GUID}")
ARGO_NS = os.environ.get("ARGO_NAMESPACE", "openshift-gitops")
ACME_APP = os.environ.get("ACME_APP_NAME", f"acme-apps-{GUID}")
# Comma-separated gitlab paths for deploy fan-out (AO-owned apps).
AO_APP_PATHS = [
    p.strip()
    for p in os.environ.get("AO_APP_PATHS", "").split(",")
    if p.strip()
]
POLL_SEC = int(os.environ.get("POLL_SECONDS", "15"))
VERIFY_TLS = os.environ.get("VERIFY_TLS", "false").lower() in ("1", "true", "yes")
# ADR-039: Merged canvas polls PaC; do not POST pipelinerun_terminal by default.
POST_BUILD_EVENTS = os.environ.get("POST_BUILD_EVENTS", "false").lower() in (
    "1",
    "true",
    "yes",
)
# Optional: narrow Deploy POSTs to apps named in the acme-deployment promote
# commit (ADR-049). Without token/URL, fall back to all AO_APP_PATHS.
GITLAB_URL = os.environ.get("GITLAB_URL", "").rstrip("/")
DEPLOY_GITLAB_PATH = os.environ.get(
    "DEPLOY_GITLAB_PATH", f"acme-{GUID}/acme-deployment"
)
# PaC promote commit title: "promote benefits-mgmt-app to <sha>"
_PROMOTE_RE = re.compile(r"promote\s+([a-z0-9][a-z0-9-]*)\s+to\s+", re.I)
_gitlab_token_cache: str | None = None


def gitlab_token() -> str:
    """Env override, else build-{guid}/gitlab-pac-token (ADR-049)."""
    global _gitlab_token_cache
    env = os.environ.get("GITLAB_TOKEN", "")
    if env:
        return env
    if _gitlab_token_cache is not None:
        return _gitlab_token_cache
    code, sec = k8s_request(
        "GET", f"/api/v1/namespaces/{BUILD_NS}/secrets/gitlab-pac-token"
    )
    if code != 200:
        print(f"gitlab-pac-token: {code} — promote-scoped Deploy disabled")
        _gitlab_token_cache = ""
        return ""
    raw = (sec.get("data") or {}).get("token") or ""
    try:
        _gitlab_token_cache = base64.b64decode(raw).decode() if raw else ""
    except Exception:  # noqa: BLE001
        _gitlab_token_cache = ""
    return _gitlab_token_cache

ANN_BUILD = "lightwell.io/eda-build-signaled"
ANN_DEPLOY = "lightwell.io/eda-deploy-signaled"

# Process-local deploy idempotency. Argo may strip CR annotations on
# self-heal of acme-apps-* from git; without this, every poll re-POSTs.
_deploy_signaled: set[str] = set()

SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SA_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
APISERVER = os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
APIPORT = os.environ.get("KUBERNETES_SERVICE_PORT", "443")


def _ssl_ctx_k8s() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if os.path.exists(SA_CA_PATH):
        ctx.load_verify_locations(SA_CA_PATH)
    return ctx


def _ssl_ctx_eda() -> ssl.SSLContext | None:
    if VERIFY_TLS:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _token() -> str:
    with open(SA_TOKEN_PATH, encoding="utf-8") as f:
        return f.read().strip()


def k8s_request(
    method: str,
    path: str,
    body: dict | None = None,
) -> tuple[int, Any]:
    url = f"https://{APISERVER}:{APIPORT}{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx_k8s(), timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            parsed = json.loads(raw) if raw else {"message": str(e)}
        except json.JSONDecodeError:
            parsed = {"message": raw or str(e)}
        return e.code, parsed


def post_eda(payload: dict) -> bool:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        EDA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx_eda(), timeout=30) as resp:
            print(f"EDA POST {payload.get('type')} → HTTP {resp.status} {payload}")
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        print(f"EDA POST failed HTTP {e.code}: {e.read().decode()[:300]}")
        return False
    except Exception as e:  # noqa: BLE001 — bridge must keep polling
        print(f"EDA POST error: {e}")
        return False


def patch_annotation(api_path: str, key: str, value: str) -> None:
    body = {"metadata": {"annotations": {key: value}}}
    # strategic merge via PATCH
    url_path = api_path
    code, resp = k8s_request("GET", url_path)
    if code != 200:
        print(f"skip annotate get {url_path}: {code} {resp}")
        return
    meta = resp.setdefault("metadata", {})
    anns = meta.setdefault("annotations", {}) or {}
    if anns.get(key) == value:
        return
    anns[key] = value
    meta["annotations"] = anns
    # Use merge-patch
    data = json.dumps({"metadata": {"annotations": {key: value}}}).encode()
    full = f"https://{APISERVER}:{APIPORT}{url_path}"
    req = urllib.request.Request(
        full,
        data=data,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/merge-patch+json",
            "Accept": "application/json",
        },
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx_k8s(), timeout=30) as resp:
            print(f"annotated {url_path} {key}={value} HTTP {resp.status}")
    except Exception as e:  # noqa: BLE001
        print(f"annotate failed {url_path}: {e}")


def pr_terminal_status(pr: dict) -> str | None:
    for cond in (pr.get("status") or {}).get("conditions") or []:
        if cond.get("type") == "Succeeded":
            status = cond.get("status")
            reason = cond.get("reason") or ""
            if status == "True":
                return "Succeeded"
            if status == "False":
                # Tekton uses Failed / Cancelled / PipelineRunTimeout etc.
                if reason in ("Cancelled", "PipelineRunCancelled"):
                    return "Cancelled"
                return "Failed"
    return None


def gitlab_path_from_pr(pr: dict) -> str:
    labels = (pr.get("metadata") or {}).get("labels") or {}
    org = labels.get("pipelinesascode.tekton.dev/url-org", "")
    repo = labels.get(
        "pipelinesascode.tekton.dev/url-repository",
        labels.get("pipelinesascode.tekton.dev/repository", ""),
    )
    if org and repo:
        return f"{org}/{repo}"
    return ""


def is_push_pr(pr: dict) -> bool:
    labels = (pr.get("metadata") or {}).get("labels") or {}
    anns = (pr.get("metadata") or {}).get("annotations") or {}
    event = labels.get("pipelinesascode.tekton.dev/event-type") or anns.get(
        "pipelinesascode.tekton.dev/event-type", ""
    )
    return event == "push" or event == ""


def scan_pipelineruns() -> None:
    code, data = k8s_request(
        "GET",
        f"/apis/tekton.dev/v1/namespaces/{BUILD_NS}/pipelineruns?limit=100",
    )
    if code != 200:
        print(f"list pipelineruns: {code} {data}")
        return
    for pr in data.get("items") or []:
        meta = pr.get("metadata") or {}
        name = meta.get("name", "")
        anns = meta.get("annotations") or {}
        if not is_push_pr(pr):
            continue
        status = pr_terminal_status(pr)
        if not status:
            continue
        if anns.get(ANN_BUILD) == status:
            continue
        path = gitlab_path_from_pr(pr)
        if not path:
            print(f"PR {name}: no gitlab_path labels — skip")
            continue
        if POST_BUILD_EVENTS:
            ok = post_eda(
                {
                    "type": "pipelinerun_terminal",
                    "guid": GUID,
                    "gitlab_path": path,
                    "status": status,
                    "pipelinerun": name,
                }
            )
            if not ok:
                continue
        else:
            print(
                f"PR {name}: terminal {status} path={path} — "
                "skip EDA POST (ADR-039 Merged polls PaC)"
            )
        patch_annotation(
            f"/apis/tekton.dev/v1/namespaces/{BUILD_NS}/pipelineruns/{name}",
            ANN_BUILD,
            status,
        )


def app_health_sync(app: dict) -> tuple[str, str]:
    st = app.get("status") or {}
    health = ((st.get("health") or {}).get("status")) or ""
    sync = ((st.get("sync") or {}).get("status")) or ""
    return health, sync


def app_deploy_revision(app: dict) -> str:
    """Git revision (or reconcile stamp) that changes on each promote/sync.

    Idempotency used to key only on Synced/Healthy, so after prime or the first
    deploy every later promote was ignored (annotation never changed). Include
    the synced revision so each acme-deployment bump can fire Deploy again.
    """
    st = app.get("status") or {}
    rev = (st.get("sync") or {}).get("revision") or ""
    if rev:
        return str(rev)
    op = st.get("operationState") or {}
    rev = ((op.get("syncResult") or {}).get("revision")) or ""
    if rev:
        return str(rev)
    hist = st.get("history") or []
    if hist:
        rev = (hist[-1] or {}).get("revision") or ""
        if rev:
            return str(rev)
    # Last resort — still changes when Argo reconciles.
    return str(st.get("reconciledAt") or "unknown")


def deploy_signal_key(sync: str, health: str, revision: str) -> str:
    return f"{sync or 'Unknown'}/{health}@{revision}"


def _ssl_ctx_gitlab() -> ssl.SSLContext | None:
    if VERIFY_TLS:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def gitlab_commit_title(revision: str) -> str:
    """Return commit title for acme-deployment @ revision, or '' if unavailable."""
    token = gitlab_token()
    if not GITLAB_URL or not token or not revision or revision == "unknown":
        return ""
    proj = urllib.parse.quote(DEPLOY_GITLAB_PATH, safe="")
    sha = urllib.parse.quote(revision, safe="")
    url = f"{GITLAB_URL}/api/v4/projects/{proj}/repository/commits/{sha}"
    req = urllib.request.Request(
        url,
        headers={"PRIVATE-TOKEN": token, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx_gitlab(), timeout=20) as resp:
            data = json.loads(resp.read().decode())
            return (data.get("title") or data.get("message") or "").split("\n", 1)[0]
    except Exception as e:  # noqa: BLE001
        print(f"gitlab commit {revision[:12]}…: {e}")
        return ""


def deploy_paths_for_revision(revision: str) -> list[str]:
    """Prefer the app(s) named in the PaC promote commit; else all AO paths.

    Shared Argo app-of-apps goes Healthy on any promote. Signaling every AO
    path starts a Deploy run with no SNOW child for untouched apps (ADR-049).
    """
    default = AO_APP_PATHS or [f"acme-{GUID}/wire-transfer-svc"]
    title = gitlab_commit_title(revision)
    if not title:
        return default
    apps = _PROMOTE_RE.findall(title)
    if not apps:
        print(f"promote parse: no app in commit title {title!r} — fan-out all")
        return default
    matched: list[str] = []
    for app in apps:
        for path in default:
            if path == app or path.endswith("/" + app):
                if path not in matched:
                    matched.append(path)
    if not matched:
        print(f"promote parse: apps={apps} not in AO_APP_PATHS — fan-out all")
        return default
    print(f"promote parse: title={title!r} → paths={matched}")
    return matched


def scan_argo_app() -> None:
    code, app = k8s_request(
        "GET",
        f"/apis/argoproj.io/v1alpha1/namespaces/{ARGO_NS}/applications/{ACME_APP}",
    )
    if code != 200:
        print(f"get application {ACME_APP}: {code} {app}")
        return
    health, sync = app_health_sync(app)
    if not health:
        return
    revision = app_deploy_revision(app)
    # Only signal terminal-ish deploy outcomes (match EDA rules).
    if health == "Healthy" and sync == "Synced":
        signal_key = deploy_signal_key(sync, health, revision)
    elif health in ("Degraded", "Missing"):
        signal_key = deploy_signal_key(sync or "Unknown", health, revision)
    else:
        return  # Progressing / Suspended etc. — wait

    anns = (app.get("metadata") or {}).get("annotations") or {}
    if signal_key in _deploy_signaled or anns.get(ANN_DEPLOY) == signal_key:
        _deploy_signaled.add(signal_key)
        return

    paths = deploy_paths_for_revision(revision)
    print(
        f"argo {ACME_APP}: {sync}/{health} rev={revision[:12]}… → "
        f"EDA argo_app_health for {len(paths)} path(s)"
    )
    all_ok = True
    for path in paths:
        ok = post_eda(
            {
                "type": "argo_app_health",
                "guid": GUID,
                "gitlab_path": path,
                "sync": sync or "Unknown",
                "health": health,
                "argo_app": ACME_APP,
                "revision": revision,
            }
        )
        all_ok = all_ok and ok
    if all_ok:
        _deploy_signaled.add(signal_key)
        patch_annotation(
            f"/apis/argoproj.io/v1alpha1/namespaces/{ARGO_NS}/applications/{ACME_APP}",
            ANN_DEPLOY,
            signal_key,
        )


def main() -> None:
    print(
        f"cicd-eda-bridge starting guid={GUID} eda={EDA_URL} "
        f"build_ns={BUILD_NS} app={ACME_APP} paths={AO_APP_PATHS}"
    )
    # Prime: mark currently-terminal objects as already signaled so we don't
    # storm EDA on bridge restart for old PipelineRuns / already-Healthy apps.
    prime = os.environ.get("PRIME_WITHOUT_POST", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if prime:
        code, data = k8s_request(
            "GET",
            f"/apis/tekton.dev/v1/namespaces/{BUILD_NS}/pipelineruns?limit=100",
        )
        if code == 200:
            for pr in data.get("items") or []:
                status = pr_terminal_status(pr)
                if not status or not is_push_pr(pr):
                    continue
                name = pr["metadata"]["name"]
                anns = pr["metadata"].get("annotations") or {}
                if anns.get(ANN_BUILD):
                    continue
                patch_annotation(
                    f"/apis/tekton.dev/v1/namespaces/{BUILD_NS}/pipelineruns/{name}",
                    ANN_BUILD,
                    status,
                )
        code, app = k8s_request(
            "GET",
            f"/apis/argoproj.io/v1alpha1/namespaces/{ARGO_NS}/applications/{ACME_APP}",
        )
        if code == 200:
            health, sync = app_health_sync(app)
            if health == "Healthy" and sync == "Synced":
                key = deploy_signal_key(sync, health, app_deploy_revision(app))
                anns = (app.get("metadata") or {}).get("annotations") or {}
                ann = anns.get(ANN_DEPLOY) or ""
                if not ann:
                    # Never signaled — prime without POSTing (cold start).
                    _deploy_signaled.add(key)
                    patch_annotation(
                        f"/apis/argoproj.io/v1alpha1/namespaces/{ARGO_NS}/applications/{ACME_APP}",
                        ANN_DEPLOY,
                        key,
                    )
                elif "@" not in ann:
                    # Legacy sticky Synced/Healthy — leave annotation so the
                    # first scan POSTs once for the current revision (catch-up).
                    print(
                        f"legacy {ANN_DEPLOY}={ann!r} — next scan will POST "
                        f"for rev={key.split('@')[-1][:12]}…"
                    )
                else:
                    # Already revision-keyed — remember so annotation wipe
                    # cannot re-storm EDA until the next promote.
                    _deploy_signaled.add(ann)
                    if ann != key:
                        _deploy_signaled.add(key)
        print("prime complete — watching for new transitions")

    while True:
        try:
            scan_pipelineruns()
            scan_argo_app()
        except Exception as e:  # noqa: BLE001
            print(f"loop error: {e}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
