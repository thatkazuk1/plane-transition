"""Entrypoint: scan text for Plane work-item references and transition them.

Reads configuration from environment variables (see README.md / action.yml)
and never logs PLANE_API_TOKEN.
"""

from __future__ import annotations

import json
import os
import sys

from plane import HttpError, PlaneClient
from plane.models.work_items import UpdateWorkItem

from parse import DEFAULT_KEYWORDS, parse

STATE_GROUPS = {"backlog", "unstarted", "started", "completed", "cancelled"}


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

    if not workspace_slug:
        print("PLANE_WORKSPACE_SLUG is required", file=sys.stderr)
        return 1 if fail_on_error else 0

    refs = parse(text, keywords=keywords, require_keyword=require_keyword, prefixes=prefixes or None)

    client = PlaneClient(base_url=base_url, api_key=token)

    results = []
    hard_error = False
    state_cache: dict[str, tuple[str, list]] = {}

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
            state_cache[project_id] = (target_uuid, states_response.results)

        target_uuid, _states = state_cache[project_id]

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
