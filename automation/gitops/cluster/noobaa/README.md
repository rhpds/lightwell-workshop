# NooBaa object storage

Standalone NooBaa (MCG) for Lightwell clusters that do not have ODF.

The tenant TPA chart expects the standard `openshift-storage` consumers:
an `ObjectBucketClaim` using storage class `openshift-storage.noobaa.io`
and the S3 endpoint `https://s3-openshift-storage.<domain>:443`. A CNV
pool provides those through external ODF; an AWS pool provides only EBS
storage classes, so NooBaa must be installed separately.

The chart is ported from `rhpds/dev-day-roadshow`
(`automation/gitops/cluster/noobaa`), which in turn ports
[rhpds/platform-engineering-workshop#6](https://github.com/rhpds/platform-engineering-workshop/pull/6).

## Enabling

Set the `noobaa` values on the bootstrap chart:

```yaml
noobaa:
  enabled: true
  name: noobaa
  namespace: openshift-storage
  channel: stable-4.22
  backingStore:
    storageClass: gp3-csi
```

| Key | Default | Notes |
| --- | --- | --- |
| `enabled` | `false` | Enable on AWS pools; leave disabled on CNV pools with ODF |
| `name` | `noobaa` | NooBaa system and child Application name |
| `namespace` | `openshift-storage` | Consumers depend on this namespace |
| `channel` | `stable-4.22` | Must match the OCP version / catalog |
| `backingStore.storageClass` | `ocs-external-storagecluster-ceph-rbd` | Use a supported RWO class (`gp3-csi` on AWS) |

AgnosticV sets these through
`ocp4_workload_gitops_bootstrap_helm_values` on the cluster catalog item.

## Behavior

- OperatorGroup (wave `-3`), Subscription (wave `-2`), then NooBaa and
  BackingStore (wave `-1`) inside the child Application.
- `dbType: postgres`; the NooBaa operator manages its own CNPG instance
  scoped to `openshift-storage`.
- A PostSync Job waits up to 30 minutes for NooBaa `Ready` and the
  backing store `Ready/OPTIMAL` before the Application reports healthy.
- The NooBaa operator creates the `openshift-storage.noobaa.io` OBC
  storage class on demand, and the `s3` route in `openshift-storage`
  resolves to `s3-openshift-storage.<domain>`.

## Storage footprint

DB volume 50 Gi plus three 50 Gi backing-store volumes: ~200 Gi and
four PVCs per cluster, in addition to per-tenant workloads.

## Validation

```bash
helm dependency build automation/gitops/cluster/noobaa --skip-refresh
helm lint automation/gitops/cluster/noobaa
```

Fresh-order validation on both an AWS and a CNV cluster is required
before promoting beyond dev.
