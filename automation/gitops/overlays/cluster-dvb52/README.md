# cluster-dvb52 overlay

Manual SDLC deploy for workshop cluster `cluster-dvb52` and tenant **`dvb52-1`**.

```bash
# 1. Create secrets in sdlc-control-plane (see ../../secrets/README.md)
# 2. Apply OpenCode control plane
kubectl apply -k gitops/overlays/cluster-dvb52/

# 3. Re-run tenant eda-bootstrap + set sdlc.edaWebhookUrl on bootstrap-tenant, then nexus-reconcile
```

Argo CD apps in `gitops/argocd/applications/` still point at `sdlc-opencode` GitHub; use this overlay for fork/local testing until repo URLs align.
