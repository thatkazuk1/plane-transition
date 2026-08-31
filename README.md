# plane-transition

Scan text for Plane work-item references and transition them on merge.

## Table of Contents

- [About the Project](#about-the-project)
- [Project Status](#project-status)
- [Usage](#usage)
  - [GitHub Actions](#github-actions)
  - [Forgejo Actions](#forgejo-actions)
  - [Also: PR opened → In Progress](#also-pr-opened--in-progress)
  - [Inputs](#inputs)
  - [Output](#output)
- [Getting Started](#getting-started)
  - [Dependencies](#dependencies)
  - [Technology Stack](#technology-stack)
  - [Third-party Services](#third-party-services)
- [Installation & Development](#installation--development)
  - [Setting Up](#setting-up)
  - [Development](#development)
  - [Testing](#testing)
- [How to Get Help](#how-to-get-help)
- [Contributing](#contributing)
- [Authors](#authors)
  - [Repo Activity](#repo-activity)
- [License](#license)

## About the Project

`plane-transition` scans text — typically a merged pull request's title and body — for
work-item references like `HOMELABSTA-22` preceded by a closing keyword (`closes`, `fixes`,
`resolves`, ...), and transitions each matching [Plane](https://plane.so) work item to a target
state. It's the "merge the PR, watch the ticket move to Done" behaviour Plane's own GitHub
integration provides, minus the Pro-gate that applies even to self-hosted instances — the REST
API and API tokens are available on Community.

It ships as a single container: a Docker `action.yml` wrapper for GitHub Actions `uses:`, and
the same image works with a plain `docker run` from any other CI system (Forgejo Actions, in
particular — see [Usage](#usage)).

One-way only, deliberately: git → Plane. No reverse sync, no comments posted back to the PR or
the Plane item. That's the whole point of keeping this simple.

## Project Status

[![CI](https://github.com/thatkazuk1/plane-transition/actions/workflows/ci.yml/badge.svg)](https://github.com/thatkazuk1/plane-transition/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Active. Wired into [`infra-stackdoc`](https://github.com/thatkazuk1/infra-stackdoc) (GitHub
Actions) and [`kazuki/homelab`](https://forgejo.ts.kazuki.uk/kazuki/homelab) (Forgejo Actions).

## Usage

### GitHub Actions

```yaml
name: Plane sync
on:
  pull_request:
    types: [closed]
jobs:
  transition:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - uses: thatkazuk1/plane-transition@v1   # or an exact vX.Y.Z tag, for a harder pin
        with:
          plane-base-url: https://plane.kazuki.uk
          plane-workspace-slug: shokunbi
          plane-api-token: ${{ secrets.PLANE_API_TOKEN }}
          identifier-prefixes: HOMELABSTA
          target-state: Done
          text: |
            ${{ github.event.pull_request.title }}

            ${{ github.event.pull_request.body }}
```

`uses:` pins a git ref (tag/branch/SHA) of *this* repo, not a container image — `action.yml`'s
`runs.image` is itself pinned to the published `ghcr.io` image's immutable digest, so any tag
you reference always resolves to the same container. Don't put an image digest directly on the
`uses:` line; GitHub/Forgejo can't resolve that as a ref.

### Forgejo Actions

Confirmed live (2026-08-31, against `forgejo.ts.kazuki.uk`) that Forgejo Actions resolves an
external `uses:` the same way GitHub Actions does, so the workflow above works unmodified
(`runs-on: docker`, same `uses:` line). If a given Forgejo runner can't resolve external
actions, fall back to a plain `docker run`:

```yaml
name: Plane sync
on:
  pull_request:
    types: [closed]
jobs:
  transition:
    if: ${{ github.event.pull_request.merged == 'true' }}
    runs-on: docker
    steps:
      - name: Transition referenced Plane work items
        env:
          PLANE_BASE_URL: https://plane.kazuki.uk
          PLANE_WORKSPACE_SLUG: shokunbi
          PLANE_API_TOKEN: ${{ secrets.PLANE_API_TOKEN }}
          PT_PREFIXES: HOMELAB
          PT_TARGET_STATE: Done
          PT_TEXT: |
            ${{ github.event.pull_request.title }}

            ${{ github.event.pull_request.body }}
        run: |
          docker run --rm \
            -e PLANE_BASE_URL -e PLANE_WORKSPACE_SLUG -e PLANE_API_TOKEN \
            -e PT_PREFIXES -e PT_TARGET_STATE -e PT_TEXT \
            ghcr.io/thatkazuk1/plane-transition:v1
```

### Also: PR opened → In Progress

The same action handles other trigger points — just a different job (or a second workflow)
listening to `types: [opened, reopened]` instead of `[closed]`, with different `keywords` and
`target-state`:

```yaml
on:
  pull_request:
    types: [opened, reopened]
jobs:
  start:
    runs-on: ubuntu-latest
    steps:
      - uses: thatkazuk1/plane-transition@v1
        with:
          plane-base-url: https://plane.kazuki.uk
          plane-workspace-slug: shokunbi
          plane-api-token: ${{ secrets.PLANE_API_TOKEN }}
          identifier-prefixes: HOMELABSTA
          target-state: started
          keywords: start,starts,started
          pr-url: ${{ github.event.pull_request.html_url }}
          text: |
            ${{ github.event.pull_request.title }}

            ${{ github.event.pull_request.body }}
```

Nothing in `plane-transition` needs to change for this — `target-state`, `keywords`, and
`pr-url` are all just config. One safety net is built in: the tool refuses to move a work item
*backward* in the workflow (`backlog < unstarted < started < completed/cancelled`). A stale
`Starts FOO-1` PR reopened after `FOO-1` is already Done won't drag it back to In Progress.

### Inputs

| env | `action.yml` input | required | default |
|---|---|---|---|
| `PLANE_BASE_URL` | `plane-base-url` | for self-hosted | `https://api.plane.so` |
| `PLANE_WORKSPACE_SLUG` | `plane-workspace-slug` | yes | — |
| `PLANE_API_TOKEN` | `plane-api-token` | yes | — |
| `PT_TEXT` | `text` | yes | — |
| `PT_PREFIXES` | `identifier-prefixes` | no | *(empty ⇒ match any `[A-Z][A-Z0-9]+-\d+`)* |
| `PT_TARGET_STATE` | `target-state` | no | `Done` |
| `PT_KEYWORDS` | `keywords` | no | `close,closes,closed,fix,fixes,fixed,resolve,resolves,resolved,complete,completes,completed` |
| `PT_REQUIRE_KEYWORD` | `require-keyword` | no | `true` |
| `PT_DRY_RUN` | `dry-run` | no | `false` |
| `PT_FAIL_ON_ERROR` | `fail-on-error` | no | `false` |
| `PT_PR_URL` | `pr-url` | no | *(empty ⇒ don't link)* |

If `PLANE_API_TOKEN` is empty, the tool prints `no token, skipping` and exits 0 rather than
failing — this lets a repo mirror without the secret configured no-op safely instead of
breaking CI. The token itself is never logged, in any code path.

If `pr-url` is set, it's attached as a link on each transitioned (or already-in-target-state)
work item — checked against existing links first, so re-runs don't create duplicates. A link
failure is logged but never fails the run; it's a best-effort enrichment, not the tool's core
job.

### Output

`transitioned` — a JSON array of `{identifier, from_state, to_state, status, dry_run}`, where
`status` is one of `transitioned`, `already_in_state`, `skipped_not_found`, `skipped_backward`,
or `error`. A human-readable summary is also written to `$GITHUB_STEP_SUMMARY` when that env var
is set (both GitHub and Forgejo Actions set it).

## Getting Started

### Dependencies

- Python 3.13
- Docker (for building/running the action image locally)

### Technology Stack

- [`plane-sdk`](https://pypi.org/project/plane-sdk/) — official Python client for the Plane
  REST API, pinned to an exact version (pre-1.0, breaking changes between minors)
- Plain `re`-based parsing, no NLP dependency
- `pytest` + `ruff` for tests and linting
- Docker, packaged as a `ghcr.io` image consumed via GitHub Actions' `uses:` or a bare
  `docker run`

### Third-party Services

- [Plane](https://plane.so) — self-hosted (`PLANE_COMMUNITY`) at `plane.kazuki.uk` for this
  deployment, or any Plane Cloud/self-hosted instance via `plane-base-url`. Needs a
  workspace-scoped API token (Workspace Settings → API Tokens).

## Installation & Development

### Setting Up

```bash
git clone https://github.com/thatkazuk1/plane-transition.git
cd plane-transition
python3 -m venv .venv && . .venv/bin/activate
pip install ruff pytest plane-sdk==0.2.23
```

### Development

```bash
PYTHONPATH=src PLANE_API_TOKEN=... PLANE_WORKSPACE_SLUG=shokunbi PT_TEXT="Closes FOO-1" \
  python src/plane_transition.py
```

Or build and run the container the same way CI does:

```bash
docker build -t plane-transition:local .
docker run --rm -e PLANE_API_TOKEN=... -e PLANE_WORKSPACE_SLUG=shokunbi -e PT_TEXT="Closes FOO-1" \
  plane-transition:local
```

### Testing

```bash
pytest tests/ -v
ruff check src/ tests/
```

`tests/test_parse.py` covers the text-parsing logic (`src/parse.py`) end to end with no network
calls. There's no automated test for the Plane-facing half (`src/plane_transition.py`) — it was
verified manually against a live instance (dry run, then a real transition, then idempotency,
404-skip, and missing-token-skip, on a throwaway work item created and deleted for the purpose).

## How to Get Help

Open an [issue](https://github.com/thatkazuk1/plane-transition/issues) for bugs, questions, or
feature requests. There's no dedicated support channel or SLA — this is a small project with a
single maintainer, checked periodically rather than continuously.

## Contributing

This is a personal-infrastructure tool, not an open-contribution project. If you spot an issue,
open one; there is no PR template or review process beyond that. Adding a fourth (or fifth)
consumer repo needs no change here — see [Usage](#usage) for the workflow shape, pointed at the
new repo's `identifier-prefixes`.

**[Back to top](#table-of-contents)**

## Authors

**Desmond Edem** ([@thatkazuk1](https://github.com/thatkazuk1)) — sole maintainer and author.

### Repo Activity

[![Commit Activity](https://img.shields.io/github/commit-activity/m/thatkazuk1/plane-transition)](https://github.com/thatkazuk1/plane-transition/commits/master)

## License

MIT — see [LICENSE](LICENSE).
