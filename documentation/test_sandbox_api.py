import argparse
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_PYTHON_CODE = """print("Hello from AICCEL Sandbox")"""
DEFAULT_JAVASCRIPT_CODE = """console.log("Hello from AICCEL Sandbox")"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test the AICCEL Sandbox API with an API key."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("AICCEL_BASE_URL", "http://127.0.0.1:8000"),
        help="AICCEL API base URL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("AICCEL_API_KEY", ""),
        help="AICCEL API key. Defaults to AICCEL_API_KEY env var.",
    )
    parser.add_argument(
        "--language",
        choices=["python", "javascript", "js"],
        default=os.getenv("AICCEL_SANDBOX_LANGUAGE", "python"),
        help="Sandbox runtime language.",
    )
    parser.add_argument(
        "--code",
        default=os.getenv("AICCEL_SANDBOX_CODE", "").strip(),
        help="Inline code to execute.",
    )
    parser.add_argument(
        "--code-file",
        default="",
        help="Optional path to a file containing the code to execute.",
    )
    parser.add_argument(
        "--input-text",
        default=os.getenv("AICCEL_SANDBOX_INPUT", ""),
        help="Optional stdin text passed to the sandbox process.",
    )
    return parser


def load_code(args: argparse.Namespace) -> str:
    if args.code_file:
        with open(args.code_file, "r", encoding="utf-8") as handle:
            return handle.read()
    if args.code:
        return args.code
    if args.language in {"javascript", "js"}:
        return DEFAULT_JAVASCRIPT_CODE
    return DEFAULT_PYTHON_CODE


def main() -> int:
    args = build_parser().parse_args()
    api_key = args.api_key.strip()
    if not api_key:
        print("Missing API key. Set AICCEL_API_KEY or pass --api-key.", file=sys.stderr)
        return 1

    try:
        code = load_code(args)
    except OSError as exc:
        print(f"Unable to read code file: {exc}", file=sys.stderr)
        return 1

    payload = {
        "language": args.language,
        "code": code,
        "input_text": args.input_text,
    }
    endpoint = f"{args.base_url.rstrip('/')}/v1/lab/execute"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
            data = json.loads(response_body)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}", file=sys.stderr)
        print(error_body, file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 3

    print("Sandbox API test")
    print(f"Endpoint: {endpoint}")
    print(f"Language: {data.get('language')}")
    print(f"Exit code: {data.get('exit_code')}")
    print(f"Timed out: {data.get('timed_out')}")
    print(f"Duration (ms): {data.get('duration_ms')}")

    stdout = data.get("stdout", "")
    stderr = data.get("stderr", "")
    print("\nSTDOUT:")
    print(stdout if stdout else "(empty)")
    print("\nSTDERR:")
    print(stderr if stderr else "(empty)")

    print("\nRaw JSON response:")
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
