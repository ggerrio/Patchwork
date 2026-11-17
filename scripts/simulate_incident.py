"""Simulate a production error incident against the local Patchwork API."""

import argparse
import asyncio
import json
import sys

import httpx


async def simulate(
    *,
    api_url: str,
    repo_owner: str,
    repo_name: str,
    base_branch: str,
    poll: bool,
) -> int:
    payload = {
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "base_branch": base_branch,
        "error_type": "ZeroDivisionError",
        "error_message": "division by zero",
        "stack_trace": (
            "Traceback (most recent call last):\n"
            '  File "demo_target/billing.py", line 7, in calculate_unit_price\n'
            "    return total_amount / quantity\n"
            "ZeroDivisionError: division by zero"
        ),
        "file_path": "demo_target/billing.py",
        "line_number": 7,
    }

    async with httpx.AsyncClient(base_url=api_url.rstrip("/"), timeout=20.0) as client:
        resp = await client.post("/v1/incidents", json=payload)
        print(f"POST /v1/incidents -> HTTP {resp.status_code}")
        print(json.dumps(resp.json(), indent=2))

        if resp.status_code not in (200, 202):
            return 1

        data = resp.json()
        incident_id = data.get("id")
        if not poll or not incident_id:
            return 0

        print(f"\nPolling incident {incident_id} ...")
        terminal = {
            "AWAITING_APPROVAL",
            "APPROVED_PR_OPENED",
            "REJECTED",
            "FAILED_MAX_RETRIES",
            "ESCALATED_TO_HUMAN",
        }
        for _ in range(30):
            await asyncio.sleep(2.0)
            detail_resp = await client.get(f"/v1/incidents/{incident_id}")
            if detail_resp.status_code != 200:
                print(f"GET /v1/incidents/{incident_id} -> HTTP {detail_resp.status_code}")
                return 1
            detail = detail_resp.json()
            status = detail["status"]
            print(
                f"  status={status} retries={detail['retry_count']} "
                f"tokens={detail['total_tokens']} traces={len(detail.get('traces', []))}"
            )
            if status in terminal:
                print("\nFinal Incident State:")
                print(json.dumps(detail, indent=2))
                return 0

    print("Timed out waiting for terminal incident status.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate a Patchwork incident.")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--repo-owner", default="ggerrio")
    parser.add_argument("--repo-name", default="Patchwork")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--no-poll", action="store_true", help="Do not poll for completion.")
    args = parser.parse_args()

    return asyncio.run(
        simulate(
            api_url=args.api_url,
            repo_owner=args.repo_owner,
            repo_name=args.repo_name,
            base_branch=args.base_branch,
            poll=not args.no_poll,
        )
    )


if __name__ == "__main__":
    sys.exit(main())

