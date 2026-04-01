import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_TEXT = (
    "Customer Jane Doe can be reached at jane@acme.com or +1-212-555-0180. "
    "Her SSN is 123-45-6789 and she works at Acme Health."
)


def main() -> int:
    api_key = os.environ.get("AICCEL_API_KEY", "").strip()
    if not api_key:
        print("Missing AICCEL_API_KEY environment variable.", file=sys.stderr)
        return 1

    base_url = os.environ.get("AICCEL_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    workspace_id = os.environ.get("AICCEL_WORKSPACE_ID", "").strip()
    text = os.environ.get("AICCEL_PII_TEXT", DEFAULT_TEXT)

    payload = {
        "text": text,
        "reversible": True,
        "remove_email": True,
        "remove_phone": True,
        "remove_person": True,
        "remove_blood_group": True,
        "remove_passport": True,
        "remove_pancard": True,
        "remove_organization": True,
    }

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    if workspace_id:
        headers["X-Workspace-ID"] = workspace_id

    request = urllib.request.Request(
        url=f"{base_url}/v1/engine/security/process",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            print(f"HTTP {response.status}")
            print("Feature: engine.security")
            print(f"Blocked: {data.get('blocked')}")
            print(f"Risk score: {data.get('risk_score')}")
            print("Detected markers:", ", ".join(data.get("detected_markers", [])) or "(none)")
            print("Sanitized text:")
            print(data.get("sanitized_text", ""))
            print("\nFull JSON:")
            print(json.dumps(data, indent=2))
            return 0
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}", file=sys.stderr)
        print(error_body, file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
