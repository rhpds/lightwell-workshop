#!/usr/bin/env python3
"""Watch tenant PipelineRuns + Acme Argo Application; POST lifecycle events to EDA.

Emits the same JSON shapes as ao-trigger-helper/trigger-cicd-signal.sh so the
existing EDA rules (pipelinerun_terminal / argo_app_health) fire AO build/deploy
triggers. Idempotent via annotations on the watched objects.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
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

ANN_BUILD = "lightwell.io/eda-build-signaled"
ANN_DEPLOY = "lightwell.io/eda-deploy-signaled"

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
        ok = post_eda(
            {
                "type": "pipelinerun_terminal",
                "guid": GUID,
                "gitlab_path": path,
                "status": status,
                "pipelinerun": name,
            }
        )
        if ok:
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
    # Only signal terminal-ish deploy outcomes (match EDA rules).
    if health == "Healthy" and sync == "Synced":
        signal_key = f"{sync}/{health}"
    elif health in ("Degraded", "Missing"):
        signal_key = f"{sync or 'Unknown'}/{health}"
    else:
        return  # Progressing / Suspended etc. — wait

    anns = (app.get("metadata") or {}).get("annotations") or {}
    if anns.get(ANN_DEPLOY) == signal_key:
        return

    paths = AO_APP_PATHS or [f"acme-{GUID}/wire-transfer-svc"]
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
            }
        )
        all_ok = all_ok and ok
    if all_ok:
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
                anns = (app.get("metadata") or {}).get("annotations") or {}
                if not anns.get(ANN_DEPLOY):
                    patch_annotation(
                        f"/apis/argoproj.io/v1alpha1/namespaces/{ARGO_NS}/applications/{ACME_APP}",
                        ANN_DEPLOY,
                        f"{sync}/{health}",
                    )
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
