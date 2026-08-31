"""Entrypoint: scan text for Plane work-item references and transition them.

Reads configuration from environment variables (see README.md / action.yml)
and never logs PLANE_API_TOKEN.
"""

from __future__ import annotations

import json
import os
import sys

from plane import HttpError, PlaneClient
from plane.models.work_items import CreateWorkItemLink, UpdateWorkItem

from parse import DEFAULT_KEYWORDS, parse

STATE_GROUPS = {"backlog", "unstarted", "started", "completed", "cancelled"}

# Ordinal position of each state group in the workflow. Used to refuse a
# transition that would move a work item backward (e.g. a stale "Starts
# FOO-1" PR reopened after FOO-1 is already Done shouldn't drag it back to
# In Progress).
GROUP_ORDER = {
    "backlog": 0,
    "unstarted": 1,
    "started": 2,
    "completed": 3,
    "cancelled": 3,
}


def is_backward(current_group: str | None, target_group: str | None) -> bool:
    """True if current_group -> target_group would move backward in the
    workflow. Unknown/missing groups never block (fail open)."""
    if current_group is None or target_group is None:
        return False
    return GROUP_ORDER.get(current_group, -1) > GROUP_ORDER.get(target_group, -1)


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list_env(name: str, default: tuple[str, ...] = ()) -> list[str]:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_target_state(states: list, target: str) -> str:
    """Resolve PT_TARGET_STATE to a state UUID.

    Matches by name (case-insensitive) first; if the target equals a known
    state group name, falls back to the first state in that group.
    """
    target_lower = target.strip().lower()
    for state in states:
        if state.name.lower() == target_lower:
            return state.id
    if target_lower in STATE_GROUPS:
        for state in states:
            if state.group == target_lower:
                return state.id
    raise ValueError(f"Could not resolve target state {target!r} against available states")


def _attach_pr_link(
    client: PlaneClient, workspace_slug: str, project_id: str, work_item_id: str, pr_url: str, identifier: str
) -> None:
    """Best-effort: attach pr_url as a link on the work item, unless already
    linked. Never raises - a link failure shouldn't fail the transition."""
    try:
        existing = client.work_items.links.list(workspace_slug, project_id, work_item_id)
        if any(link.url == pr_url for link in existing.results):
            return
        client.work_items.links.create(
            workspace_slug, project_id, work_item_id, CreateWorkItemLink(url=pr_url, title="Linked PR")
        )
        print(f"{identifier}: linked PR")
    except HttpError as e:
        print(f"{identifier}: could not link PR (status {e.status_code})", file=sys.stderr)


def run() -> int:
    token = os.environ.get("PLANE_API_TOKEN", "")
    fail_on_error = _bool_env("PT_FAIL_ON_ERROR", False)

    if not token:
        print("no token, skipping")
        return 0

    base_url = os.environ.get("PLANE_BASE_URL", "https://api.plane.so")
    workspace_slug = os.environ.get("PLANE_WORKSPACE_SLUG", "")
    text = os.environ.get("PT_TEXT", "")
    prefixes = _list_env("PT_PREFIXES")
    target_state = os.environ.get("PT_TARGET_STATE", "Done")
    keywords = _list_env("PT_KEYWORDS", DEFAULT_KEYWORDS)
    require_keyword = _bool_env("PT_REQUIRE_KEYWORD", True)
    dry_run = _bool_env("PT_DRY_RUN", False)
    pr_url = os.environ.get("PT_PR_URL", "").strip()

    if not workspace_slug:
        print("PLANE_WORKSPACE_SLUG is required", file=sys.stderr)
        return 1 if fail_on_error else 0

    refs = parse(text, keywords=keywords, require_keyword=require_keyword, prefixes=prefixes or None)

    client = PlaneClient(base_url=base_url, api_key=token)

    results = []
    hard_error = False
    state_cache: dict[str, tuple[str, dict]] = {}

    for prefix, seq in refs:
        identifier = f"{prefix}-{seq}"
        try:
            work_item = client.work_items.retrieve_by_identifier(workspace_slug, prefix, seq)
        except HttpError as e:
            if e.status_code == 404:
                print(f"{identifier}: skipped (not found)")
                results.append({"identifier": identifier, "status": "skipped_not_found"})
                continue
            print(f"{identifier}: error (status {e.status_code})", file=sys.stderr)
            results.append({"identifier": identifier, "status": "error"})
            hard_error = True
            continue

        project_id = work_item.project
        current_state = work_item.state

        if project_id not in state_cache:
            try:
                states_response = client.states.list(workspace_slug, project_id)
            except HttpError as e:
                print(f"{identifier}: error listing states (status {e.status_code})", file=sys.stderr)
                results.append({"identifier": identifier, "status": "error"})
                hard_error = True
                continue
            try:
                target_uuid = resolve_target_state(states_response.results, target_state)
            except ValueError as e:
                print(f"{identifier}: {e}", file=sys.stderr)
                results.append({"identifier": identifier, "status": "error"})
                hard_error = True
                continue
            state_by_id = {s.id: s for s in states_response.results}
            state_cache[project_id] = (target_uuid, state_by_id)

        target_uuid, state_by_id = state_cache[project_id]
        target_group = state_by_id[target_uuid].group
        current_group = state_by_id[current_state].group if current_state in state_by_id else None

        if current_state == target_uuid:
            print(f"{identifier}: already in target state")
            results.append(
                {
                    "identifier": identifier,
                    "from_state": current_state,
                    "to_state": target_uuid,
                    "status": "already_in_state",
                    "dry_run": dry_run,
                }
            )
            if pr_url and not dry_run:
                _attach_pr_link(client, workspace_slug, project_id, work_item.id, pr_url, identifier)
            continue

        if is_backward(current_group, target_group):
            print(f"{identifier}: skipped (would move backward: {current_group} -> {target_group})")
            results.append(
                {
                    "identifier": identifier,
                    "from_state": current_state,
                    "to_state": target_uuid,
                    "status": "skipped_backward",
                    "dry_run": dry_run,
                }
            )
            continue

        if not dry_run:
            try:
                client.work_items.update(
                    workspace_slug, project_id, work_item.id, UpdateWorkItem(state=target_uuid)
                )
            except HttpError as e:
                print(f"{identifier}: error updating (status {e.status_code})", file=sys.stderr)
                results.append({"identifier": identifier, "status": "error"})
                hard_error = True
                continue

        print(f"{identifier}: {current_state} -> {target_uuid}{' (dry run)' if dry_run else ''}")
        results.append(
            {
                "identifier": identifier,
                "from_state": current_state,
                "to_state": target_uuid,
                "status": "transitioned",
                "dry_run": dry_run,
            }
        )
        if pr_url and not dry_run:
            _attach_pr_link(client, workspace_slug, project_id, work_item.id, pr_url, identifier)

    output = json.dumps(results)
    print(f"transitioned={output}")

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        with open(step_summary_path, "a", encoding="utf-8") as f:
            f.write("### plane-transition\n\n")
            if not results:
                f.write("No work-item references found.\n")
            f.writelines(f"- `{r['identifier']}`: {r['status']}\n" for r in results)

    github_output_path = os.environ.get("GITHUB_OUTPUT")
    if github_output_path:
        with open(github_output_path, "a", encoding="utf-8") as f:
            f.write(f"transitioned={output}\n")

    if fail_on_error and hard_error:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
