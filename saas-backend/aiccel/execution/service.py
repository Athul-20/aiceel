# aiccel/execution/service.py
import io
import time
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd
import requests

from .protocol import ExecutionResult, Executor


@dataclass
class ServiceExecutionResult:
    success: bool
    output: str
    error: Optional[str]
    dataframe: Optional[pd.DataFrame]
    execution_time_ms: float

class MicroserviceExecutor(Executor):
    """
    Executes code by sending it to a remote AICCEL Runner microservice.
    Highest isolation level.
    """

    def __init__(self, endpoint: str = "http://localhost:8080"):
        self.endpoint = endpoint.rstrip("/")

    def execute(
        self,
        code: str,
        dataframe: Optional[pd.DataFrame] = None,
        context: Optional[dict[str, Any]] = None
    ) -> ExecutionResult:
        start_time = time.perf_counter()

        # 1. Prepare Request
        df_json = None
        if dataframe is not None:
            df_json = dataframe.to_json()

        payload = {
            "code": code,
            "dataframe_json": df_json,
            "context": context or {}
        }

        try:
            # 2. Call Service
            response = requests.post(
                f"{self.endpoint}/execute",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # 3. Parse Result
            result_df = dataframe
            if data.get("dataframe_json"):
                result_df = pd.read_json(io.StringIO(data["dataframe_json"]))

            return ServiceExecutionResult(
                success=data["success"],
                output=data["output"],
                error=data.get("error"),
                dataframe=result_df,
                execution_time_ms=data["execution_time_ms"]
            )

        except Exception as e:
            return ServiceExecutionResult(
                success=False,
                output="",
                error=f"Microservice Connection Error: {e!s}",
                dataframe=dataframe,
                execution_time_ms=(time.perf_counter() - start_time) * 1000
            )
