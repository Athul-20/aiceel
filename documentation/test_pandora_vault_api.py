import argparse
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_PLAINTEXT = "Highly confidential sample for Pandora Vault"
DEFAULT_PASSPHRASE = "StrongPassphrase123!"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test the AICCEL Pandora Vault API with an API key."
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
        "--plaintext",
        default=os.getenv("AICCEL_VAULT_PLAINTEXT", DEFAULT_PLAINTEXT),
        help="Plaintext value to encrypt.",
    )
    parser.add_argument(
        "--passphrase",
        default=os.getenv("AICCEL_VAULT_PASSPHRASE", DEFAULT_PASSPHRASE),
        help="Passphrase used for both encrypt and decrypt.",
    )
    parser.add_argument(
        "--decrypt-only",
        action="store_true",
        help="Skip encrypt and decrypt an existing blob passed via --encrypted-blob.",
    )
    parser.add_argument(
        "--encrypted-blob",
        default=os.getenv("AICCEL_VAULT_BLOB", ""),
        help="Existing encrypted blob for decrypt-only mode.",
    )
    return parser


def post_json(url: str, api_key: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    args = build_parser().parse_args()
    api_key = args.api_key.strip()
    if not api_key:
        print("Missing API key. Set AICCEL_API_KEY or pass --api-key.", file=sys.stderr)
        return 1

    base_url = args.base_url.rstrip("/")
    encrypt_url = f"{base_url}/v1/engine/security/vault/encrypt"
    decrypt_url = f"{base_url}/v1/engine/security/vault/decrypt"

    try:
        if args.decrypt_only:
            encrypted_blob = args.encrypted_blob.strip()
            if not encrypted_blob:
                print("Missing encrypted blob. Pass --encrypted-blob or set AICCEL_VAULT_BLOB.", file=sys.stderr)
                return 1
        else:
            encrypt_payload = {
                "plaintext": args.plaintext,
                "passphrase": args.passphrase,
            }
            encrypt_data = post_json(encrypt_url, api_key, encrypt_payload)
            encrypted_blob = encrypt_data.get("encrypted_blob", "")

            print("Pandora Vault encrypt test")
            print(f"Endpoint: {encrypt_url}")
            print(f"Algorithm: {encrypt_data.get('algorithm')}")
            print(f"Generated at: {encrypt_data.get('generated_at')}")
            print("Encrypted blob:")
            print(encrypted_blob if encrypted_blob else "(empty)")
            print("\nEncrypt response JSON:")
            print(json.dumps(encrypt_data, indent=2))
            print("\n" + "-" * 72 + "\n")

        decrypt_payload = {
            "encrypted_blob": encrypted_blob,
            "passphrase": args.passphrase,
        }
        decrypt_data = post_json(decrypt_url, api_key, decrypt_payload)

        print("Pandora Vault decrypt test")
        print(f"Endpoint: {decrypt_url}")
        print(f"Generated at: {decrypt_data.get('generated_at')}")
        print("Recovered plaintext:")
        print(decrypt_data.get("plaintext", ""))
        print("\nDecrypt response JSON:")
        print(json.dumps(decrypt_data, indent=2))
        return 0
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}", file=sys.stderr)
        print(error_body, file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Unexpected failure: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
