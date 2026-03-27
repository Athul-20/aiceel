# aiccel/execution/local.py
import contextlib
import datetime
import io
import json
import math
import random
import re
import string
import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from .protocol import ExecutionResult, Executor


@dataclass
class LocalExecutionResult:
    success: bool
    output: str
    error: Optional[str]
    dataframe: Optional[pd.DataFrame]
    execution_time_ms: float

class LocalExecutor(Executor):
    """
    Executes code in the local process using a restricted builtin scope.
    This is the fastest but least isolated execution mode.
    """

    @staticmethod
    def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
        allowed = ["pandas", "numpy", "re", "random", "string", "datetime", "math", "json", "pd", "np"]
        if name in allowed or any(a in name for a in allowed):
            return __import__(name, globals, locals, fromlist, level)
        raise ImportError(f"Module '{name}' is not allowed in this restricted environment")

    SAFE_BUILTINS = {
        "abs": abs, "all": all, "any": any, "bool": bool,
        "complex": complex, "dict": dict, "divmod": divmod,
        "enumerate": enumerate, "filter": filter, "float": float,
        "frozenset": frozenset, "hash": hash, "hex": hex,
        "int": int, "isinstance": isinstance, "issubclass": issubclass,
        "iter": iter, "len": len, "list": list, "map": map,
        "max": max, "min": min, "next": next, "oct": oct,
        "ord": ord, "pow": pow, "print": print, "range": range,
        "repr": repr, "reversed": reversed, "round": round,
        "set": set, "slice": slice, "sorted": sorted,
        "str": str, "sum": sum, "tuple": tuple, "type": type,
        "zip": zip, "None": None, "True": True, "False": False,
        "__import__": _restricted_import.__func__
    }

    def execute(
        self,
        code: str,
        dataframe: Optional[pd.DataFrame] = None,
        context: Optional[dict[str, Any]] = None
    ) -> ExecutionResult:
        start_time = time.perf_counter()
        output_buffer = io.StringIO()

        execution_scope = {
            "df": dataframe,
            "pd": pd,
            "np": np,
            "re": re,
            "random": random,
            "string": string,
            "datetime": datetime,
            "math": math,
            "json": json,
            "__builtins__": self.SAFE_BUILTINS
        }

        if context:
            execution_scope.update(context)

        try:
            with contextlib.redirect_stdout(output_buffer):
                exec(code, execution_scope)

            end_time = time.perf_counter()
            result_df = execution_scope.get("df")

            return LocalExecutionResult(
                success=True,
                output=output_buffer.getvalue(),
                error=None,
                dataframe=result_df if isinstance(result_df, pd.DataFrame) else dataframe,
                execution_time_ms=(end_time - start_time) * 1000
            )
        except Exception as e:
            end_time = time.perf_counter()
            return LocalExecutionResult(
                success=False,
                output=output_buffer.getvalue(),
                error=f"{type(e).__name__}: {e!s}",
                dataframe=dataframe,
                execution_time_ms=(end_time - start_time) * 1000
            )
