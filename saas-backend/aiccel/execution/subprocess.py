# aiccel/execution/subprocess.py
import io
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from .protocol import ExecutionResult, Executor


@dataclass
class SubprocessExecutionResult:
    success: bool
    output: str
    error: Optional[str]
    dataframe: Optional[pd.DataFrame]
    execution_time_ms: float

class SubprocessExecutor(Executor):
    """
    Executes code in a separate Python subprocess.
    Provides process-level isolation and can be constrained by OS limits.
    """

    RUNNER_TEMPLATE = """
import pandas as pd
import json
import io
import sys
import contextlib

def run():
    # Load data from stdin
    input_data = json.load(sys.stdin)
    code = input_data['code']
    df_json = input_data.get('df_json')

    df = None
    if df_json:
        df = pd.read_json(io.StringIO(df_json))

    output_buffer = io.StringIO()
    scope = {
        "df": df,
        "pd": pd,
        "__builtins__": __builtins__
    }

    success = True
    error = None

    try:
        with contextlib.redirect_stdout(output_buffer):
            exec(code, scope)
    except Exception as e:
        success = False
        error = f"{type(e).__name__}: {str(e)}"

    # Prepare result
    result_df = scope.get("df")
    result_df_json = None
    if isinstance(result_df, pd.DataFrame):
        result_df_json = result_df.to_json()

    result = {
        "success": success,
        "output": output_buffer.getvalue(),
        "error": error,
        "df_json": result_df_json
    }

    print("---AICCEL_RESULT_START---")
    print(json.dumps(result))
    print("---AICCEL_RESULT_END---")

if __name__ == "__main__":
    run()
"""

    def execute(
        self,
        code: str,
        dataframe: Optional[pd.DataFrame] = None,
        context: Optional[dict[str, Any]] = None
    ) -> ExecutionResult:
        start_time = time.perf_counter()

        df_json = dataframe.to_json() if dataframe is not None else None
        input_payload = json.dumps({
            "code": code,
            "df_json": df_json
        })

        try:
            # Spawn subprocess
            process = subprocess.Popen(
                [sys.executable, "-c", self.RUNNER_TEMPLATE],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(input=input_payload, timeout=30)

            # Parse result from stdout
            if "---AICCEL_RESULT_START---" in stdout:
                parts = stdout.split("---AICCEL_RESULT_START---")
                json_part = parts[1].split("---AICCEL_RESULT_END---")[0].strip()
                data = json.loads(json_part)

                result_df = dataframe
                if data.get("df_json"):
                    result_df = pd.read_json(io.StringIO(data["df_json"]))

                return SubprocessExecutionResult(
                    success=data["success"],
                    output=data["output"],
                    error=data["error"] or (stderr if not data["success"] else None),
                    dataframe=result_df,
                    execution_time_ms=(time.perf_counter() - start_time) * 1000
                )
            else:
                return SubprocessExecutionResult(
                    success=False,
                    output=stdout,
                    error=f"Subprocess crashed: {stderr or 'No error info'}",
                    dataframe=dataframe,
                    execution_time_ms=(time.perf_counter() - start_time) * 1000
                )

        except subprocess.TimeoutExpired:
            process.kill()
            return SubprocessExecutionResult(
                success=False,
                output="",
                error="Execution timed out (30s)",
                dataframe=dataframe,
                execution_time_ms=(time.perf_counter() - start_time) * 1000
            )
        except Exception as e:
            return SubprocessExecutionResult(
                success=False,
                output="",
                error=f"Subprocess error: {e!s}",
                dataframe=dataframe,
                execution_time_ms=(time.perf_counter() - start_time) * 1000
            )
