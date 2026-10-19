# Lab screenshot tooling

Captures Showroom screenshots as the **tenant user** in a plain browser — no
Showroom iframe, i.e. what a student sees opening the URL directly — and draws
the red click-here callouts used in Modules 2 and 3.

## Use

```bash
python3 -m venv .venv && .venv/bin/pip install playwright pillow
.venv/bin/python -m playwright install chromium

export LW_USER=user-<guid>
export LW_PASS=<tenant password>        # from the Argo app helm values
export LW_GITLAB=https://gitlab-gitlab.<domain>
export LW_AO=https://ao.<domain>

# one-off: establishes the session for GitLab + AO
.venv/bin/python shoot.py login x

# capture, with a red box around whatever the student must click
.venv/bin/python shoot.py ao-workflows "$LW_AO/workflows" \
  --box 'a:has-text("Lightwell Remediation — Start")'
```

Boxes are resolved from the live DOM via Playwright selectors, so nothing is
hand-measured and a UI change moves the box rather than silently mis-placing it.

| flag | effect |
|---|---|
| `--box SEL` | red rectangle around the first match (repeatable) |
| `--click SEL` | click before shooting |
| `--clickxy X,Y` | click at CSS coordinates (canvas controls with no stable selector) |
| `--wait SEL` | wait for a selector first |
| `--sleep MS` | settle time before the shot |
| `--full` | full-page capture |

Output lands in `/tmp/shots/raw/`. Crop to the region of interest before
committing — full-page GitLab captures run to ~6000px tall and are unreadable
inline.

## Conventions

- Images live in `content/modules/ROOT/images/`, prefixed `m3-` for Module 3.
- Red is pure `#FF0000`, stroke ~0.45% of image width, matching the Module 2
  Renovate screenshots.
- Shoot as the tenant user, never cluster admin — the lab is a tenant view.
- Alt text containing a comma must be quoted: AsciiDoc parses
  `image::f.png[a, b]` positionally and would turn the rest into `width`.
