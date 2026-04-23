#!/usr/bin/env python3
"""Run pre-defined pygeoapi process requests from a JSON file.

Usage:
    python scripts/run_api_tests.py --cases tests/api_cases.example.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass
class CaseResult:
    name: str
    process_id: str
    ok: bool
    status_code: int
    detail: str


def _load_cases(cases_path: Path) -> list[dict[str, Any]]:
    if not cases_path.is_file():
        raise FileNotFoundError(f"Cases file not found: {cases_path}")

    with cases_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Cases file must contain a JSON array.")
    return data


def _replace_placeholders(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: _replace_placeholders(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_placeholders(v, context) for v in value]
    if isinstance(value, str):
        out = value
        for k, v in context.items():
            out = out.replace(f"{{{{{k}}}}}", str(v))
        return out
    return value


def _extract_session_id(response_json: Any) -> str | None:
    if not isinstance(response_json, dict):
        return None

    # Support both legacy and current session key names.
    if "session_id" in response_json and response_json["session_id"]:
        return str(response_json["session_id"])
    if "sessionid" in response_json and response_json["sessionid"]:
        return str(response_json["sessionid"])
    return None


def _default_expected_status(mode: str) -> int:
    return 200 if mode == "sync" else 202


def _execute_case(
    base_url: str,
    case: dict[str, Any],
    context: dict[str, Any],
    timeout: int,
    mode: str,
) -> tuple[CaseResult, dict[str, Any] | None]:
    name = case.get("name", "<unnamed>")
    process_id = case.get("process")
    body = case.get("body", {})
    expected_status = int(case.get("expected_status", _default_expected_status(mode)))

    if not process_id:
        return (
            CaseResult(name=name, process_id="<missing>", ok=False, status_code=0, detail="Missing 'process' in case"),
            None,
        )

    resolved_body = _replace_placeholders(body, context)
    # pygeoapi process execution expects {"inputs": {...}}.
    # Accept either already-wrapped payloads or shorthand case bodies.
    execution_payload = resolved_body if isinstance(resolved_body, dict) and "inputs" in resolved_body else {"inputs": resolved_body}
    url = f"{base_url.rstrip('/')}/processes/{process_id}/execution"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if mode == "async":
        # OGC API Processes async execution hint.
        headers["Prefer"] = "respond-async"

    try:
        response = requests.post(url, json=execution_payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        return (
            CaseResult(name=name, process_id=process_id, ok=False, status_code=0, detail=f"Request error: {exc}"),
            None,
        )

    try:
        response_json = response.json()
        response_preview = json.dumps(response_json, ensure_ascii=True)[:240]
    except ValueError:
        response_json = None
        response_preview = response.text[:240]

    ok = response.status_code == expected_status
    detail = response_preview if ok else f"Expected {expected_status}, got {response.status_code}. Response: {response_preview}"
    return (
        CaseResult(
            name=name,
            process_id=process_id,
            ok=ok,
            status_code=response.status_code,
            detail=detail,
        ),
        response_json if isinstance(response_json, dict) else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run saved JSON API test cases against LARE pygeoapi.")
    parser.add_argument("--base-url", default="http://localhost:5000", help="Base URL of pygeoapi service")
    parser.add_argument("--cases", default="tests/api_cases.example.json", help="Path to JSON cases file")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds")
    parser.add_argument(
        "--mode",
        choices=("sync", "async"),
        default="sync",
        help="Execution mode for all cases. Async sends 'Prefer: respond-async'.",
    )
    args = parser.parse_args()

    cases_path = Path(args.cases)
    try:
        cases = _load_cases(cases_path)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 2

    context: dict[str, Any] = {}
    results: list[CaseResult] = []

    print(f"Running {len(cases)} API cases against {args.base_url} in {args.mode} mode ...")
    for idx, case in enumerate(cases, start=1):
        result, response_json = _execute_case(args.base_url, case, context, args.timeout, args.mode)
        results.append(result)
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {idx:02d}. {result.name} ({result.process_id}) -> HTTP {result.status_code}")
        if not result.ok:
            print(f"       {result.detail}")

        if response_json:
            session_id = _extract_session_id(response_json)
            if session_id:
                # Keep both placeholders working: {{session_id}} and {{sessionid}}.
                context["session_id"] = session_id
                context["sessionid"] = session_id

    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    print(f"\nDone. Passed: {passed}, Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
