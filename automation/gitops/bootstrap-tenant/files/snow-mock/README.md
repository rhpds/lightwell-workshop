# snow-mock (vendored)

Lightweight ServiceNow ITSM mock used by `bootstrap-tenant` (`snow-<guid>`).

Upstream origin: [redhat-ads-tech/snow-mock](https://github.com/redhat-ads-tech/snow-mock).
This copy lives under the tenant chart so GitOps can deploy comment-capable
builds without waiting on a Quay publish (ConfigMap + UBI Python; optional
Dockerfile for ImageStream builds).

## Incidents list filters

`GET /api/v1/incidents` supports (among others):

| Param | Meaning |
|-------|---------|
| `cmdb_ci` | Exact match on `cmdb_ci` (AO stamps `gitlab_path` here on child create) |
| `guid` | Match `guid` field, or `guid: <value>` / `guid=<value>` in description |
| `parent_incident` | Children of that parent |
| `open_only` | Only non-terminal states |
| `limit` / `offset` | Pagination (default sort `opened_at` desc) |

Example lifecycle lookup:
`GET /api/v1/incidents?cmdb_ci=acme-cng2l/wire-transfer-svc&guid=cng2l&open_only=1&limit=5`

## Comments API

| Method | Path | Body |
|--------|------|------|
| `GET` | `/api/v1/incidents/{number}/comments` | — |
| `POST` | `/api/v1/incidents/{number}/comments` | `{ "body": "...", "created_by": "...", "type": "additional_comments\|work_notes" }` |
| `GET` | `/api/v1/incidents/{number}` | embeds `comments[]` |
| `PATCH` | `/api/v1/incidents/{number}` | `additional_comments` / `work_notes` / `comment` → journal entries |

Aliases accepted on POST: `body`, `text`, `comment`, `value`, `work_notes`, `additional_comments`.
`POST /api/v1/incidents` accepts optional `guid` (stored on the record for list filter).

## Comment UI (Markdown + autolink)

Bodies are stored as plain text. The SPA renders a **small Markdown subset**
(escape-first — raw HTML in `body` is never executed):

- Headings `#` / `##` / `###`
- Bullet / numbered lists
- Horizontal rules (`---`)
- `**bold**`, `*italic*`, `` `code` ``
- `[label](https://…)` and bare `http(s)://…` autolinks (new tab)

Use this for AO remediation comments so Activity / Work notes look readable.
