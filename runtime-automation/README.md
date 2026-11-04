# runtime-automation

This directory is empty of playbooks on purpose, and it must exist. See
[ADR-062](../ADR.md#adr-062--the-content-repo-must-ship-runtime-automation-even-when-unused).

## Why it has to be here

The Showroom deployment can carry a Zero Touch `runner` sidecar
(`quay.io/rhpds/zt-runner`). Its health endpoint is not a plain liveness ping —
it reports **503** when the runtime-automation directory is missing:

```python
_base = '/app' if os.path.isdir('/app/runtime-automation') else '/showroom/repo'
RUNTIME_DIR = os.path.join(os.environ.get('BASE_DIR', _base), 'runtime-automation')
...
if not os.path.isdir(RUNTIME_DIR):
    checks['runtime_dir'] = f'missing: {RUNTIME_DIR}'
    status_code = 503
```

`showroom-single-pod` 2.1.x mounts only the cloned repo (`/showroom/repo`) into
the runner, so it resolves to `/showroom/repo/runtime-automation` — this
directory, as cloned from `main`. If it is absent the container fails its
liveness probe three times (~70 s), the kubelet sends SIGTERM, gunicorn shuts
down gracefully (**exit 0, `Completed`**), and `restartPolicy: Always` turns
that into `CrashLoopBackOff`. The pod then never becomes Ready, so the Service
has no endpoints and the Showroom Route answers 503 even though `nginx`,
`content` and `terminal` are healthy.

The same failure shows up in Ansible as a wait loop that gives up:
`changed: false`, `attempts: 60`, pod `Ready=False` with
`containers with unready status: [runner]`.

## What is *not* implemented here

This lab is tab-driven (terminal, console, Nexus, Renovate, TPA, GitLab,
Ansible Orchestrator, Snow, ArgoCD). There are no Zero Touch
solve/validate playbooks, so `/config` returns `{}` and the Zero Touch UI
offers no modules. This README exists so the sidecar can be healthy — not
to claim the lab grades itself.

## Contract, if modules are added later

One directory per module, with files that the runner serves as
`/setup/<module>`, `/solve/<module>` and `/validate/<module>`:

```
runtime-automation/
├── requirements.txt      # optional: pip install before the first request
├── requirements.yml      # optional: ansible-galaxy collections
└── module-01/
    ├── setup.yml
    ├── solve.yml
    └── validation.yml    # uses the lab_check_fail / validation_check plugins
```

Extra vars are injected from the `showroom-userdata` ConfigMap
(`/user_data/user_data.yml`): `user`, `guid`, `student_ns`, `student_ns2`,
`student_user`, `bastion_*`, and `k8s_kubeconfig` where the tenant supplies one.

## Verify

```bash
oc -n user-<guid>-showroom exec deploy/showroom -c runner -- \
  curl -sS -o /dev/null -w '%{http_code}\n' localhost:8501/health     # 200
oc -n user-<guid>-showroom get pod -o wide                            # Ready 4/4
```

The fix only reaches a seat on its next pod (the `git-cloner` init container
clones `main` at pod start), so after merging:

```bash
oc -n user-<guid>-showroom rollout restart deploy/showroom
```
