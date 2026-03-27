
"""
AICCEL MCP Feature Server
=========================

Exposes powerful AICCEL features as an MCP Server:
1. Pandora: LLM-powered Data Transformation
2. Jailbreak Guard: AI Safety & Injection Detection

Usage:
    python -m aiccel.mcp_features
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path


# Ensure package is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aiccel.mcp import MCPServerBuilder


# Configuration
SERVER_NAME = "aiccel-features"
SERVER_VERSION = "1.0.0"

# --- Helper Functions ---

def get_llm_provider():
    """Get the best available LLM provider based on env vars."""
    from aiccel.providers import GeminiProvider, GroqProvider, OpenAIProvider

    if os.environ.get("GOOGLE_API_KEY"):
        return GeminiProvider()
    elif os.environ.get("OPENAI_API_KEY"):
        return OpenAIProvider()
    elif os.environ.get("GROQ_API_KEY"):
        return GroqProvider()
    else:
        # Fallback specifically for local testing if no keys (Pandora will fail but tool will run)
        # In production this should raise
        raise ValueError("No API Key found. Please set GOOGLE_API_KEY, OPENAI_API_KEY, or GROQ_API_KEY.")

# --- Server Definition ---

builder = MCPServerBuilder(SERVER_NAME, SERVER_VERSION)

@builder.tool(
    name="check_safety",
    description="Check a text prompt for jailbreak attempts or unsafe content.",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "The text prompt to check"}
        },
        "required": ["prompt"]
    }
)
async def check_safety(prompt: str) -> str:
    """Check if a prompt is safe using AICCEL's JailbreakGuard (Local Model)."""
    print(f"Calling aiccel.jailbreak for prompt: '{prompt[:20]}...'", file=sys.stderr)

    try:
        # Lazy import as requested to speed up initial server boot
        from aiccel.jailbreak import check_prompt

        # This will trigger model download on first run if not cached
        print("Running check_prompt (this may take a while to download model)...", file=sys.stderr)
        is_safe = check_prompt(prompt)
        print(f"check_prompt finished. Result: {is_safe}", file=sys.stderr)

        if is_safe:
            return "SAFE: The prompt appears safe."
        else:
            return "UNSAFE: Jailbreak or unsafe content detected."

    except ImportError:
        error_msg = "Error: 'transformers' library not found. Please install it to use JailbreakGuard."
        print(error_msg, file=sys.stderr)
        return error_msg
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        return f"Error running Safety Check: {e!s}"

@builder.tool(
    name="transform_data",
    description="Transform a CSV/Excel file using natural language instructions via Pandora.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the data file (.csv, .xlsx, .json)"},
            "instruction": {"type": "string", "description": "Natural language instruction for transformation"}
        },
        "required": ["file_path", "instruction"]
    }
)
async def transform_data(file_path: str, instruction: str) -> str:
    """Run Pandora transformation on a data file."""
    # Lazy import to avoid startup cost
    from aiccel.pandora import Pandora

    try:
        # Validate path
        p = Path(file_path)
        if not p.exists():
            return f"Error: File not found at {file_path}"

        # Initialize Provider & Pandora
        try:
            llm = get_llm_provider()
        except ValueError as e:
            return f"Configuration Error: {e}"

        pandora = Pandora(llm=llm, verbose=True)

        # Run Transformation
        # Note: Pandora operations are typically sync but heavy.
        # Ideally run in executor, but for demo we run directly (Pandora handles some internal execution)
        result_df = pandora.do(p, instruction)

        if result_df.empty:
            return "Warning: Transformation resulted in an empty DataFrame."

        # Save result
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{p.stem}_processed_{timestamp}{p.suffix}"
        output_path = p.parent / output_filename

        if p.suffix.lower() == '.csv':
            result_df.to_csv(output_path, index=False)
        elif p.suffix.lower() in ['.xlsx', '.xls']:
            result_df.to_excel(output_path, index=False)
        elif p.suffix.lower() == '.json':
            result_df.to_json(output_path, orient='records')
        else:
             result_df.to_csv(output_path, index=False)

        return f"Success! Transformed data saved to: {output_path}\nRows: {len(result_df)}"

    except Exception as e:
        return f"Pandora Error: {e!s}"

# Build the server instance
server = builder.build()

if __name__ == "__main__":
    # Run using stdio transport by default
    asyncio.run(server.run_stdio())
