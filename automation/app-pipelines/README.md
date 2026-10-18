# Acme app pipelines

These belong in the three Acme app repos under `redhat-ads-tech`, not here.
They live in this repo only so the work is not lost: nobody on the Lightwell
side currently has push access to those repos, so they need a PR.

| File | Purpose |
|---|---|
| `.tekton/build-pull-request.yaml` | **New.** Runs on an open merge request, tests the branch, and fills the Automated Validation table in the MR body ([ADR-032](../../ADR.md)). |
| `.tekton/build-push-to-main.yaml` | Existing pipeline **plus** a `promote-to-deployment-repo` task that bumps the app's `imageTag` in `acme-deployment`, which is what makes ArgoCD deploy the remediated build. |

Copy both into each app repo's `.tekton/` directory. They are app-agnostic —
every value comes from PaC (`{{ repo_name }}`, `{{ repo_owner }}`,
`{{ pull_request_number }}`) or the Repository CR params.

Both were verified end to end on tenant `cd2fp` against
`acme-cd2fp/wire-transfer-svc`; see the Handoff entry for the run.

## Dependencies

- The PaC webhook must subscribe to **merge_request** events. It did not;
  fixed in `bootstrap-tenant/templates/build/webhook-job.yaml`.
- `report-validation` reads the `gitlab-pac-token` Secret, which the
  `build-setup` Job already creates in `build-<guid>`.
- `promote-to-deployment-repo` needs `acme-deployment` to be writable by the
  root PAT and readable by ArgoCD — it is seeded public.
