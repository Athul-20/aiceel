#!/usr/bin/env python3
"""
AICCEL Command Line Interface
==============================

A powerful CLI for interacting with the aiccel framework.

Usage:
    aiccel run "What is the weather in Tokyo?"
    aiccel chat
    aiccel tools list
    aiccel encrypt "secret data"
    aiccel decrypt <encrypted_string>
    aiccel version
"""

import argparse
import json
import os
import sys


def get_version():
    """Get aiccel version."""
    try:
        from . import __version__
        return __version__
    except ImportError:
        return "unknown"


def cmd_version(args):
    """Display version information."""
    print(f"aiccel version {get_version()}")
    print("Python:", sys.version.split()[0])
    print("Platform:", sys.platform)


def cmd_run(args):
    """Run a single query against an agent."""
    query = args.query
    provider_name = args.provider.lower()
    model = args.model
    verbose = args.verbose

    # Get API key from environment
    api_key = None
    if provider_name == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    elif provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
    elif provider_name == "groq":
        api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        print(f"Error: No API key found for {provider_name}.")
        print("Set the environment variable (e.g., GOOGLE_API_KEY, OPENAI_API_KEY, GROQ_API_KEY)")
        sys.exit(1)

    try:
        # Import provider
        if provider_name == "gemini":
            from .providers import GeminiProvider
            provider = GeminiProvider(api_key=api_key, model=model or "gemini-2.0-flash")
        elif provider_name == "openai":
            from .providers import OpenAIProvider
            provider = OpenAIProvider(api_key=api_key, model=model or "gpt-4o-mini")
        elif provider_name == "groq":
            from .providers import GroqProvider
            provider = GroqProvider(api_key=api_key, model=model or "llama3-70b-8192")
        else:
            print(f"Error: Unknown provider '{provider_name}'. Options: gemini, openai, groq")
            sys.exit(1)

        from .agent import Agent

        agent = Agent(
            provider=provider,
            name="CLI Agent",
            verbose=verbose
        )

        if verbose:
            print(f"[aiccel] Running query with {provider_name}...")

        result = agent.run(query)

        print("\n" + "="*60)
        print("RESPONSE:")
        print("="*60)
        print(result.get("response", "No response"))

        if result.get("tools_used"):
            print("\n[Tools Used]:", ", ".join(result["tools_used"]))

        if result.get("error"):
            print("\n[Error]:", result["error"])

    except Exception as e:
        print(f"Error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def cmd_chat(args):
    """Start an interactive chat session."""
    provider_name = args.provider.lower()

    # Get API key
    api_key = None
    if provider_name == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    elif provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
    elif provider_name == "groq":
        api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        print(f"Error: No API key found for {provider_name}.")
        sys.exit(1)

    try:
        # Import provider
        if provider_name == "gemini":
            from .providers import GeminiProvider
            provider = GeminiProvider(api_key=api_key)
        elif provider_name == "openai":
            from .providers import OpenAIProvider
            provider = OpenAIProvider(api_key=api_key)
        elif provider_name == "groq":
            from .providers import GroqProvider
            provider = GroqProvider(api_key=api_key)
        else:
            print(f"Error: Unknown provider '{provider_name}'")
            sys.exit(1)

        from .agent import Agent

        agent = Agent(
            provider=provider,
            name="ChatBot",
            memory_type="buffer",
            max_memory_turns=20,
            verbose=False
        )

        print("="*60)
        print("  AICCEL Interactive Chat")
        print(f"  Provider: {provider_name}")
        print("  Type 'exit' or 'quit' to end the session")
        print("  Type 'clear' to clear conversation history")
        print("="*60)
        print()

        while True:
            try:
                user_input = input("You: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit", "q"):
                    print("Goodbye!")
                    break

                if user_input.lower() == "clear":
                    agent.clear_memory()
                    print("[Memory cleared]")
                    continue

                result = agent.run(user_input)
                response = result.get("response", "No response")

                print(f"\nAgent: {response}\n")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except EOFError:
                print("\nGoodbye!")
                break

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_tools(args):
    """List available tools."""
    action = args.action

    if action == "list":
        print("\n" + "="*60)
        print("  AICCEL Built-in Tools")
        print("="*60)

        tools_info = [
            {
                "name": "SearchTool",
                "description": "Web search using Serper API",
                "import": "from aiccel import SearchTool",
                "requires": "SERPER_API_KEY"
            },
            {
                "name": "WeatherTool",
                "description": "Weather data using OpenWeatherMap",
                "import": "from aiccel import WeatherTool",
                "requires": "OPENWEATHERMAP_API_KEY"
            },
            {
                "name": "PDFRAGTool",
                "description": "PDF document Q&A with RAG",
                "import": "from aiccel.pdf_rag_tool import PDFRAGTool",
                "requires": "Embedding provider"
            }
        ]

        for tool in tools_info:
            print(f"\n• {tool['name']}")
            print(f"  Description: {tool['description']}")
            print(f"  Import: {tool['import']}")
            print(f"  Requires: {tool['requires']}")

        print("\n" + "="*60)
        print("\nTo create custom tools, inherit from aiccel.tools.BaseTool")
        print()
    else:
        print(f"Unknown action: {action}")
        print("Available actions: list")


def cmd_encrypt(args):
    """Encrypt data using the secure vault."""
    try:
        from .encryption import encrypt_string

        data = args.data
        password = args.password or os.getenv("AICCEL_VAULT_PASSWORD")

        if not password:
            import getpass
            password = getpass.getpass("Enter encryption password: ")

        encrypted = encrypt_string(data, password)
        print("\nEncrypted data:")
        print(encrypted)

    except ImportError:
        print("Error: Encryption module not available. Install 'cryptography' package.")
        sys.exit(1)
    except Exception as e:
        print(f"Encryption error: {e}")
        sys.exit(1)


def cmd_decrypt(args):
    """Decrypt data using the secure vault."""
    try:
        from .encryption import decrypt_string

        encrypted = args.encrypted
        password = args.password or os.getenv("AICCEL_VAULT_PASSWORD")

        if not password:
            import getpass
            password = getpass.getpass("Enter decryption password: ")

        decrypted = decrypt_string(encrypted, password)
        print("\nDecrypted data:")
        print(decrypted)

    except ImportError:
        print("Error: Encryption module not available. Install 'cryptography' package.")
        sys.exit(1)
    except Exception as e:
        print(f"Decryption error: {e}")
        sys.exit(1)


def cmd_mask(args):
    """Mask PII in text."""
    try:
        from .privacy import mask_text

        text = args.text

        result = mask_text(
            text,
            remove_email=True,
            remove_phone=True,
            remove_person=True,
            remove_organization=True,
            remove_ssn=True,
            remove_card=True,
            remove_address=True,
            remove_dob=True,
            remove_bank_account=True,
            remove_passport=True,
            remove_pancard=True,
            remove_blood_group=True
        )

        masked = result['masked_text']
        mapping = result['mask_mapping']
        extracted = result['extracted_entities']

        print("\nMasked text:")
        print(masked)

        if args.show_mapping:
            print("\nMask Mapping:")
            print(json.dumps(mapping, indent=2))
            
            print("\nExtracted Entities Summary:")
            summary = {k: len(v) for k, v in extracted.items() if isinstance(v, list) and v}
            print(json.dumps(summary, indent=2))

    except Exception as e:
        print(f"Masking error: {e}")
        sys.exit(1)


def cmd_check(args):
    """Check environment health."""
    from .health import check_health
    check_health(verbose=args.verbose)


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="aiccel",
        description="AICCEL - AI Agent Framework CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aiccel run "What is the capital of France?"
  aiccel run "Search for AI news" --provider gemini --verbose
  aiccel chat
  aiccel tools list
  aiccel check
  aiccel version
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Version command
    version_parser = subparsers.add_parser("version", help="Show version info")
    version_parser.set_defaults(func=cmd_version)

    # Check command
    check_parser = subparsers.add_parser("check", help="Check environment health")
    check_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    check_parser.set_defaults(func=cmd_check)

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a single query")
    run_parser.add_argument("query", help="The query to run")
    run_parser.add_argument(
        "-p", "--provider",
        default="gemini",
        choices=["gemini", "openai", "groq"],
        help="LLM provider to use (default: gemini)"
    )
    run_parser.add_argument("-m", "--model", help="Specific model to use")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    run_parser.set_defaults(func=cmd_run)

    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Start interactive chat")
    chat_parser.add_argument(
        "-p", "--provider",
        default="gemini",
        choices=["gemini", "openai", "groq"],
        help="LLM provider to use (default: gemini)"
    )
    chat_parser.set_defaults(func=cmd_chat)

    # Tools command
    tools_parser = subparsers.add_parser("tools", help="Tool management")
    tools_parser.add_argument("action", choices=["list"], help="Action to perform")
    tools_parser.set_defaults(func=cmd_tools)

    # Encrypt command
    encrypt_parser = subparsers.add_parser("encrypt", help="Encrypt data")
    encrypt_parser.add_argument("data", help="Data to encrypt")
    encrypt_parser.add_argument("--password", help="Encryption password")
    encrypt_parser.set_defaults(func=cmd_encrypt)

    # Decrypt command
    decrypt_parser = subparsers.add_parser("decrypt", help="Decrypt data")
    decrypt_parser.add_argument("encrypted", help="Encrypted data string")
    decrypt_parser.add_argument("--password", help="Decryption password")
    decrypt_parser.set_defaults(func=cmd_decrypt)

    # Mask command
    mask_parser = subparsers.add_parser("mask", help="Mask PII in text")
    mask_parser.add_argument("text", help="Text to mask")
    mask_parser.add_argument("--show-mapping", action="store_true", help="Show mask mapping")
    mask_parser.set_defaults(func=cmd_mask)

    # Parse arguments
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Execute command
    args.func(args)


if __name__ == "__main__":
    main()
