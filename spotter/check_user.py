"""
check_user.py — Check if a user exists on a ThoughtSpot cluster
using a secret key for trusted authentication.

Usage:
    python3 check_user.py \
        --host https://your-cluster.thoughtspot.cloud \
        --secret-key YOUR_SECRET_KEY \
        --admin-user admin \
        --check-user john.doe@company.com

    # Check multiple users at once:
    python3 check_user.py \
        --host https://your-cluster.thoughtspot.cloud \
        --secret-key YOUR_SECRET_KEY \
        --admin-user admin \
        --check-user alice@company.com bob@company.com charlie@company.com
"""

import argparse
import json
import sys
import requests


def get_token(host: str, admin_user: str, secret_key: str) -> str:
    """Get a Bearer token using the cluster secret key (trusted auth)."""
    url = f"{host}/api/rest/2.0/auth/token/full"
    resp = requests.post(
        url,
        json={
            "username": admin_user,
            "secret_key": secret_key,
            "validity_time_in_sec": 300,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[ERROR] Auth failed ({resp.status_code}): {resp.text}")
        sys.exit(1)
    return resp.json()["token"]


def user_exists(host: str, token: str, username: str) -> dict:
    """
    Check if a user exists. Returns a dict with:
        found      : bool
        user_id    : str | None
        display_name: str | None
        email      : str | None
        status     : str | None   (ACTIVE / INACTIVE)
    """
    url = f"{host}/api/rest/2.0/users/search"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"user_identifier": username},
        timeout=15,
    )

    if resp.status_code == 404:
        return {"found": False, "user_id": None, "display_name": None,
                "email": None, "status": None}

    if resp.status_code != 200:
        return {"found": False, "error": f"HTTP {resp.status_code}: {resp.text}",
                "user_id": None, "display_name": None, "email": None, "status": None}

    users = resp.json()
    if not users:
        return {"found": False, "user_id": None, "display_name": None,
                "email": None, "status": None}

    # user_identifier does an exact match on username or email
    # but the API may return partial matches — confirm exact match
    match = None
    for u in users:
        if u.get("name") == username or u.get("email") == username:
            match = u
            break

    if not match:
        # fall back to first result if no exact match (name search)
        match = users[0]

    return {
        "found": True,
        "user_id":      match.get("id"),
        "display_name": match.get("display_name"),
        "email":        match.get("email"),
        "status":       match.get("account_status"),  # ACTIVE / INACTIVE
        "account_type": match.get("account_type"),    # LOCAL_USER / LDAP_USER etc.
    }


def print_result(username: str, result: dict) -> None:
    if result.get("error"):
        print(f"  ✗  {username}")
        print(f"     Error: {result['error']}")
        return

    if result["found"]:
        print(f"  ✓  {username}")
        print(f"     ID:           {result['user_id']}")
        print(f"     Display name: {result['display_name']}")
        print(f"     Email:        {result['email']}")
        print(f"     Status:       {result['status']}")
        print(f"     Account type: {result['account_type']}")
    else:
        print(f"  ✗  {username}  — NOT FOUND")


def main():
    parser = argparse.ArgumentParser(
        description="Check if one or more users exist on a ThoughtSpot cluster."
    )
    parser.add_argument("--host",        required=True,
                        help="ThoughtSpot cluster URL, e.g. https://my.thoughtspot.cloud")
    parser.add_argument("--secret-key",  required=True,
                        help="Cluster secret key (from Admin → Security Settings)")
    parser.add_argument("--admin-user",  required=True,
                        help="Admin username used to generate the auth token")
    parser.add_argument("--check-user",  nargs="+", required=True, metavar="USERNAME",
                        help="One or more usernames or email addresses to check")
    parser.add_argument("--json",        action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    host = args.host.rstrip("/")

    print(f"\nCluster : {host}")
    print(f"Checking: {', '.join(args.check_user)}\n")

    # Step 1: Authenticate
    print("Authenticating with secret key…")
    try:
        token = get_token(host, args.admin_user, args.secret_key)
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Could not connect to {host}. Check the URL and network access.")
        sys.exit(1)
    print("Auth OK\n")

    # Step 2: Check each user
    results = {}
    for username in args.check_user:
        result = user_exists(host, token, username)
        results[username] = result

    # Step 3: Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("─" * 50)
        for username, result in results.items():
            print_result(username, result)
            print()
        print("─" * 50)
        found_count = sum(1 for r in results.values() if r["found"])
        print(f"\nResult: {found_count}/{len(results)} user(s) found.\n")


if __name__ == "__main__":
    main()
