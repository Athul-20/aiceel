# aiccel/pandora.py
"""
Pandora - Secure DataFrame Transformation Engine
=================================================

AI-powered DataFrame transformations with security sandbox.

Features:
- Natural language to code transformation
- Sandboxed execution (no arbitrary code execution)
- Automatic code repair on failure
- Rich data profiling for better AI context

Security:
- AST validation before execution
- Restricted builtins and modules
- Execution timeout
- No file/network access

Example:
    from aiccel import Pandora, OpenAIProvider

    llm = OpenAIProvider(api_key="...")
    pandora = Pandora(llm)

    result_df = pandora.do(
        source="data.csv",
        instruction="Remove all rows where age < 18 and mask email addresses"
    )
"""

import ast
import json
import re
import traceback
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
import pandas as pd

from .providers import LLMProvider
from .sandbox import SandboxExecutor


class Pandora:
    """
    AI-powered DataFrame transformation engine with secure execution.

    Uses LLM to generate Python code for data transformations,
    then executes in a sandboxed environment for security.
    """

    def __init__(
        self,
        llm: LLMProvider,
        max_retries: int = 4,
        verbose: bool = True,
        timeout: float = 30.0,
        allow_unsafe: bool = False
    ):
        """
        Initialize Pandora.

        Args:
            llm: LLM provider for code generation
            max_retries: Maximum retries on failure
            verbose: Enable verbose output
            timeout: Execution timeout in seconds
            allow_unsafe: If True, bypasses sandbox (NOT RECOMMENDED)
        """
        self.llm = llm
        self.max_retries = max_retries
        self.verbose = verbose
        self.timeout = timeout
        self.allow_unsafe = allow_unsafe

        # Initialize sandbox
        self._sandbox = SandboxExecutor(timeout=timeout)

    def do(
        self,
        source: Union[str, Path, pd.DataFrame],
        instruction: str,
        safe_mode: bool = False
    ) -> pd.DataFrame:
        """
        Executes instructions on a DataFrame.

        Args:
            source: DataFrame, file path, or Path object
            instruction: Natural language instruction
            safe_mode: If True, returns original on failure instead of raising

        Returns:
            Transformed DataFrame

        Examples:
            >>> pandora.do(df, "Remove duplicate rows")
            >>> pandora.do("data.csv", "Add a column 'age_group' based on age")
            >>> pandora.do(df, "Mask all email addresses with random values")
        """
        # 1. Load Data
        try:
            df = source.copy() if isinstance(source, pd.DataFrame) else self._load(source)
        except Exception as e:
            if safe_mode:
                print(f"Pandora Load Error: {e}")
                return pd.DataFrame()
            raise e

        original_df = df.copy()  # Keep backup

        # 2. Generate Rich Context
        profile = self._profile_data(df)

        last_error = None
        history: list[str] = []
        last_code_output = ""

        for attempt in range(self.max_retries + 1):
            try:
                # 3. Construct Prompt
                if attempt == 0 or not history:
                    prompt = self._build_initial_prompt(profile, instruction)
                else:
                    prompt = self._build_repair_prompt(
                        instruction,
                        history[-1],
                        last_error,
                        last_code_output
                    )

                # 4. LLM Generation
                if self.verbose:
                    print(f"--- Pandora Thinking (Attempt {attempt+1}/{self.max_retries+1}) ---")

                raw_response = self.llm.generate(prompt, temperature=0.0, max_tokens=6000)
                code = self._extract_code(raw_response)
                history.append(code)

                # 5. Syntax Check
                ast.parse(code)

                # 6. Security Validation
                validation = self._sandbox.validate_code(code)
                if not validation['valid']:
                    raise SecurityError(
                        f"Code failed security validation: {'; '.join(validation['errors'])}"
                    )

                # 7. Execute in Sandbox
                if self.allow_unsafe:
                    # DANGEROUS: Only for trusted environments
                    result_df = self._execute_unsafe(code, df)
                else:
                    result_df = self._execute_sandboxed(code, df)

                if not isinstance(result_df, pd.DataFrame):
                    raise ValueError(
                        "The code executed but `df` variable was lost or is no longer a DataFrame."
                    )

                if self.verbose:
                    print("--- Pandora Success ---")

                return result_df

            except SecurityError as e:
                last_error = str(e)
                if self.verbose:
                    print(f"Pandora Security Error (Attempt {attempt+1}): {last_error}")
                continue

            except Exception as e:
                last_code_output = ""  # Reset output capture

                last_error = f"{type(e).__name__}: {e!s}"
                if not isinstance(e, SyntaxError):
                    tb = traceback.format_exc().split('\n')
                    last_error += "\n" + "\n".join(tb[-4:])

                if self.verbose:
                    print(f"Pandora Error (Attempt {attempt+1}): {last_error}")

                continue

        # Failure Handling
        msg = f"Pandora failed to transform data after {self.max_retries} attempts."
        if safe_mode:
            print(f"WARNING: {msg} Returning original DataFrame.")
            return original_df
        else:
            raise RuntimeError(f"{msg}\nLast Error: {last_error}")

    def _execute_sandboxed(self, code: str, df: pd.DataFrame) -> pd.DataFrame:
        """Execute code in sandbox"""
        import datetime
        import json
        import math
        import random
        import re
        import string

        import numpy as np
        import pandas as pd

        # Prepare globals with the dataframe
        globals_dict = {
            "df": df.copy(),
            "pd": pd,
            "np": np,
            "re": re,
            "random": random,
            "string": string,
            "datetime": datetime,
            "math": math,
            "json": json,
        }

        # Execute in sandbox
        result = self._sandbox.execute(code, globals_dict, validate=False)

        if not result['success']:
            raise RuntimeError(f"Sandbox execution failed: {result['error']}")

        # Extract the transformed DataFrame
        result_df = result['globals'].get('df')

        if result_df is None:
            raise ValueError("Variable 'df' was not found after execution")

        return result_df

    def _execute_unsafe(self, code: str, df: pd.DataFrame) -> pd.DataFrame:
        """
        Execute code without sandbox (DANGEROUS - only for trusted code).

        This bypasses all security checks and should only be used in
        completely isolated environments.
        """
        import contextlib
        import datetime
        import io
        import json
        import math
        import random
        import re
        import string

        import numpy as np
        import pandas as pd

        execution_scope = {
            "df": df.copy(),
            "pd": pd,
            "np": np,
            "re": re,
            "random": random,
            "string": string,
            "datetime": datetime,
            "math": math,
            "json": json
        }

        output_buffer = io.StringIO()

        with contextlib.redirect_stdout(output_buffer):
            exec(code, execution_scope)

        return execution_scope.get("df")

    def _profile_data(self, df: pd.DataFrame) -> dict[str, Any]:
        """Generates a concise statistical profile."""
        profile: dict[str, Any] = {
            "shape": df.shape,
            "columns": {},
        }

        for col in df.columns[:20]:  # Limit to first 20 columns
            dtype = str(df[col].dtype)
            col_info: dict[str, Any] = {"dtype": dtype}

            try:
                col_info["samples"] = df[col].dropna().sample(min(3, len(df))).tolist()
            except Exception:
                col_info["samples"] = df[col].head(3).tolist()

            if np.issubdtype(df[col].dtype, np.number):
                if not df[col].empty:
                    col_info["min"] = float(df[col].min())
                    col_info["max"] = float(df[col].max())
            elif df[col].dtype == 'object' or df[col].dtype.name == 'category':
                col_info["unique_count"] = int(df[col].nunique())

            profile["columns"][col] = col_info

        return profile

    def _build_initial_prompt(self, profile: dict[str, Any], instruction: str) -> str:
        return f"""
You are PANDORA, an elite Data Engineer AI.
Your goal: Transform the pandas DataFrame `df` based on the User Instruction.

DATA PROFILE:
{json.dumps(profile, indent=2, default=str)}

USER INSTRUCTION:
"{instruction}"

LIBRARIES AVAILABLE:
pandas (pd), numpy (np), re, random, string, datetime, math, json.

SECURITY RULES (IMPORTANT):
1. Do NOT use eval(), exec(), compile(), or __import__
2. Do NOT access file system (no open(), no Path operations)
3. Do NOT make network requests
4. Do NOT access private attributes (starting with _)
5. Only use the libraries listed above

CODE RULES:
1. The input dataframe is in the global variable `df`.
2. You MUST modify `df` in place or assign the result back to `df`.
3. Do NOT use markdown or ```python``` blocks. Just raw code.
4. If masking data, use `random` to ensure uniqueness if required.
5. Ensure `df` remains a pandas DataFrame at the end.

Start your code now:
"""

    def _build_repair_prompt(
        self,
        instruction: str,
        bad_code: str,
        error: Optional[str],
        output: str
    ) -> str:
        return f"""
The previous code attempt failed.

USER INSTRUCTION: "{instruction}"

FAILED CODE:
{bad_code}

EXECUTION OUTPUT (STDOUT):
{output}

ERROR MESSAGE:
{error}

SECURITY RULES (MUST FOLLOW):
1. Do NOT use eval(), exec(), compile(), or __import__
2. Do NOT access file system or network
3. Only use: pandas, numpy, re, random, string, datetime, math, json

TASK:
Fix the code logic.
1. If NameError 'df' not defined: Ensure you aren't deleting it.
2. If IndexError: Check column names in Data Profile.
3. If SecurityError: Remove any file/network/unsafe operations.
4. Return the FULL, CORRECTED Python script.
"""

    def _extract_code(self, text: str) -> str:
        """Extract Python code from LLM response"""
        text = text.strip()

        # Try to extract from markdown code block
        match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        return text

    def _load(self, path: Union[str, Path]) -> pd.DataFrame:
        """Load DataFrame from file"""
        p = Path(path)

        if p.suffix == ".csv":
            return pd.read_csv(p)
        if p.suffix in [".xlsx", ".xls"]:
            return pd.read_excel(p)
        if p.suffix == ".parquet":
            return pd.read_parquet(p)
        if p.suffix == ".json":
            return pd.read_json(p)

        raise ValueError(f"Unsupported file format: {p}")


class SecurityError(Exception):
    """Raised when code fails security validation"""
    pass
