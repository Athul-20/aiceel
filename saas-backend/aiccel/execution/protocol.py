# aiccel/execution/protocol.py
from typing import Any, Optional, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class ExecutionResult(Protocol):
    """Result of a code execution"""
    success: bool
    output: str
    error: Optional[str]
    dataframe: Optional[pd.DataFrame]
    execution_time_ms: float

class Executor(Protocol):
    """Base interface for code execution backends"""
    def execute(
        self,
        code: str,
        dataframe: Optional[pd.DataFrame] = None,
        context: Optional[dict[str, Any]] = None
    ) -> ExecutionResult:
        """Execute code and return result"""
        ...
