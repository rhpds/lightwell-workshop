# Optional Argo app-of-apps (legacy standalone SDLC gitops)

Most labs use **`bootstrap-tenant`** (`eda-bootstrap`, Nexus reconcile) instead of syncing children from `lw-sdlc-opencode/gitops`.

If you still deploy OpenCode via Kustomize:

- Base: [`../sdlc-control-plane`](../sdlc-control-plane)
- Lab overlay: [`../overlays/cluster-dvb52`](../overlays/cluster-dvb52)

See [`../docs/sdlc-argocd-integration.md`](../docs/sdlc-argocd-integration.md).

Apply parent Application (edit `repoURL` / `targetRevision` first):

```bash
kubectl apply -f automation/gitops/integration/sdlc-opencode/sdlc-opencode-app-of-apps.yaml
```
