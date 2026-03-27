# aiccel/health.py
"""
Environment Health & Dependency Checker
=======================================

Provides utilities to verify if required and optional dependencies
are installed and if environment variables are correctly set.
"""

import importlib.util
import logging
import os
import sys
from typing import Any


logger = logging.getLogger(__name__)

class DependencyChecker:
    """Checks for package and environment health."""

    # Packages to check
    REQUIRED_PACKAGES = [
        ("tenacity", "Retry logic"),
        ("pydantic", "Data validation"),
    ]

    OPTIONAL_PACKAGES = [
        ("cryptography", "Encryption & Secure Vault"),
        ("google-generativeai", "Gemini Provider"),
        ("openai", "OpenAI Provider"),
        ("groq", "Groq Provider"),
        ("FlagEmbedding", "Neural Reranker (Rerank module)"),
        ("chromadb", "Vector storage for RAG"),
        ("PyPDF2", "PDF processing"),
        ("duckduckgo-search", "Search tool"),
    ]

    # Env vars to check
    API_KEYS = [
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "ANTHROPIC_API_KEY",
        "SERPER_API_KEY",
        "OPENWEATHERMAP_API_KEY",
    ]

    @staticmethod
    def is_package_installed(package_name: str) -> bool:
        """Check if a Python package is installed."""
        return importlib.util.find_spec(package_name) is not None

    def get_health_report(self) -> dict[str, Any]:
        """Generate a comprehensive health report."""
        report = {
            "version": self._get_version(),
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "dependencies": {
                "required": [],
                "optional": []
            },
            "environment": {}
        }

        # Check required
        for pkg, desc in self.REQUIRED_PACKAGES:
            status = self.is_package_installed(pkg.split('.')[0])
            report["dependencies"]["required"].append({
                "name": pkg,
                "description": desc,
                "installed": status
            })

        # Check optional
        for pkg, desc in self.OPTIONAL_PACKAGES:
            # Handle cases like google-generativeai vs google.generativeai
            import_name = pkg.replace("-", "_")
            if pkg == "google-generativeai":
                import_name = "google.generativeai"

            status = self.is_package_installed(import_name.split('.')[0])
            report["dependencies"]["optional"].append({
                "name": pkg,
                "description": desc,
                "installed": status
            })

        # Check env vars
        for key in self.API_KEYS:
            value = os.environ.get(key)
            report["environment"][key] = {
                "set": value is not None,
                "value": f"{value[:4]}...{value[-4:]}" if value and len(value) > 8 else "***" if value else None
            }

        return report

    def _get_version(self) -> str:
        """Get framework version."""
        try:
            from . import __version__
            return __version__
        except ImportError:
            return "unknown"

def check_health(verbose: bool = False):
    """Print health report to console."""
    checker = DependencyChecker()
    report = checker.get_health_report()

    print(f"\n{'='*60}")
    print(f"  AICCEL HEALTH CHECK (v{report['version']})")
    print(f"{'='*60}")
    print(f"Python:   {report['python']}")
    print(f"Platform: {report['platform']}\n")

    print("--- Required Dependencies ---")
    all_req_ok = True
    for item in report["dependencies"]["required"]:
        status = "✅ OK" if item["installed"] else "❌ MISSING"
        if not item["installed"]: all_req_ok = False
        print(f"[{status}] {item['name']:<20} - {item['description']}")

    print("\n--- Optional Dependencies ---")
    for item in report["dependencies"]["optional"]:
        status = "✅ OK" if item["installed"] else "⚠️  OPTIONAL"
        print(f"[{status}] {item['name']:<20} - {item['description']}")

    print("\n--- Environment Variables ---")
    for key, data in report["environment"].items():
        status = "✅ SET" if data["set"] else "⚪ NOT SET"
        val = data["value"] if data["set"] else ""
        print(f"[{status}] {key:<25} {val}")

    print(f"\n{'='*60}")
    if not all_req_ok:
        print("CRITICAL: Some required dependencies are missing.")
        print("Please run: pip install aiccel[all]")
    else:
        print("System is ready for basic operation.")
    print(f"{'='*60}\n")

    return all_req_ok
