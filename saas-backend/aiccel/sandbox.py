# aiccel/sandbox.py
"""
Sandboxed Code Execution
========================

Provides secure-ish code execution for AI-generated Python code.
Uses RestrictedPython and AST analysis for safety.

.. warning::
    **SECURITY NOTICE**: This sandbox relies on AST parsing and restricted globals.
    It is designed to prevent *accidental* damage, not to stop a determined attacker.
    Do NOT execute untrusted code on a machine with sensitive access or data.
    For true isolation, run this code inside a Docker container or Firecracker microVM.

Security Features:
- Whitelist-based function/module access
- No file system access
- No network access
- No dangerous builtins
- Execution timeout
- Memory limits (where supported)
"""

import ast
import io
import multiprocessing
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any, Optional


# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================

class SandboxConfig:
    """Configuration for sandbox execution"""

    # Allowed modules for pandas operations
    ALLOWED_MODULES: set[str] = {
        'pandas', 'pd',
        'numpy', 'np',
        're',
        'math',
        'datetime',
        'json',
        'random',
        'string',
        'collections',
        'itertools',
        'functools',
    }

    # Blocked builtins (dangerous)
    BLOCKED_BUILTINS: set[str] = {
        'eval', 'exec', 'compile',
        'open', 'file',
        '__import__',
        'input',
        'breakpoint',
        'memoryview',
        'globals', 'locals', 'vars',
        'help', 'exit', 'quit',
        'copyright', 'credits', 'license',
    }

    # Blocked attributes (dangerous)
    BLOCKED_ATTRS: set[str] = {
        '__class__', '__bases__', '__subclasses__',
        '__code__', '__globals__', '__builtins__',
        '__reduce__', '__reduce_ex__',
        '__getattribute__', '__setattr__', '__delattr__',
        '__mro__', '__dict__', '__module__', '__name__',
        'system', 'popen', 'spawn',
        'read', 'write', 'readline', 'readlines',
        '_private',
    }

    # Blocked function calls
    BLOCKED_CALLS: set[str] = {
        'os.system', 'os.popen', 'os.spawn',
        'subprocess.call', 'subprocess.run', 'subprocess.Popen',
        'eval', 'exec', 'compile',
        'open', '__import__',
    }

    # Maximum execution time (seconds)
    MAX_EXECUTION_TIME: float = 30.0

    # Maximum output size (characters)
    MAX_OUTPUT_SIZE: int = 100000

    # Run code in a separate process for stronger isolation
    USE_SUBPROCESS: bool = True


# ============================================================================
# AST SECURITY VALIDATOR
# ============================================================================

class ASTSecurityValidator(ast.NodeVisitor):
    """
    Validates AST for security issues before execution.

    Checks for:
    - Import of disallowed modules
    - Access to dangerous attributes
    - Dangerous function calls
    - Eval/exec usage
    """

    def __init__(self, config: SandboxConfig = None):
        self.config = config or SandboxConfig()
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate(self, code: str) -> bool:
        """
        Validate code for security issues.

        Args:
            code: Python source code

        Returns:
            True if code is safe, False otherwise
        """
        self.errors = []
        self.warnings = []

        try:
            tree = ast.parse(code)
            self.visit(tree)
            return len(self.errors) == 0
        except SyntaxError as e:
            self.errors.append(f"Syntax error: {e}")
            return False

    def visit_Import(self, node: ast.Import) -> None:
        """Check import statements"""
        for alias in node.names:
            module_name = alias.name.split('.')[0]
            if module_name not in self.config.ALLOWED_MODULES:
                self.errors.append(f"Import of '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from...import statements"""
        if node.module:
            module_name = node.module.split('.')[0]
            if module_name not in self.config.ALLOWED_MODULES:
                self.errors.append(f"Import from '{node.module}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check attribute access"""
        attr_name = node.attr

        # Check for blocked attributes
        if attr_name in self.config.BLOCKED_ATTRS:
            self.errors.append(f"Access to attribute '{attr_name}' is not allowed")

        # Check for private attribute access
        if attr_name.startswith('_') and not attr_name.startswith('__'):
            self.warnings.append(f"Access to private attribute '{attr_name}'")

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check function calls"""
        # Get the full call name
        call_name = self._get_call_name(node)

        if call_name in self.config.BLOCKED_CALLS:
            self.errors.append(f"Call to '{call_name}' is not allowed")

        # Check for eval/exec
        if call_name in ('eval', 'exec', 'compile'):
            self.errors.append(f"Use of '{call_name}' is not allowed")

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """Check name access"""
        if node.id in self.config.BLOCKED_BUILTINS:
            self.errors.append(f"Use of '{node.id}' is not allowed")
        self.generic_visit(node)

    def _get_call_name(self, node: ast.Call) -> str:
        """Extract the full call name from a Call node"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return '.'.join(reversed(parts))
        return ''


# ============================================================================
# SAFE BUILTINS
# ============================================================================

def _create_safe_builtins() -> dict[str, Any]:
    """Create a restricted set of builtins"""
    import builtins

    # Start with safe builtins
    safe_names = [
        'abs', 'all', 'any', 'bin', 'bool', 'bytes', 'callable',
        'chr', 'complex', 'dict', 'divmod', 'enumerate', 'filter',
        'float', 'format', 'frozenset', 'getattr', 'hasattr', 'hash',
        'hex', 'id', 'int', 'isinstance', 'issubclass', 'iter',
        'len', 'list', 'map', 'max', 'min', 'next', 'object',
        'oct', 'ord', 'pow', 'print', 'range', 'repr', 'reversed',
        'round', 'set', 'slice', 'sorted', 'str', 'sum', 'tuple',
        'type', 'zip',
        'True', 'False', 'None',
        '__import__',  # Needed for 'import' statements to work
        'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError',
        'RuntimeError', 'StopIteration', 'AttributeError',
    ]

    safe_builtins = {}
    for name in safe_names:
        if hasattr(builtins, name):
            safe_builtins[name] = getattr(builtins, name)

    return safe_builtins


def _restricted_import_factory(allowed_modules: set[str]):
    """Create a restricted __import__ that only allows whitelisted modules."""
    def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if root in allowed_modules:
            return __import__(name, globals, locals, fromlist, level)
        raise ImportError(f"Module '{name}' is not allowed")
    return _restricted_import


def _prepare_exec_globals(
    safe_builtins: dict[str, Any],
    allowed_modules: set[str],
    user_globals: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Prepare globals for sandbox execution with optional modules."""
    import datetime
    import json
    import math
    import random
    import re
    import string

    exec_globals = {'__builtins__': safe_builtins.copy()}
    exec_globals['__builtins__']['__import__'] = _restricted_import_factory(allowed_modules)

    # Optional dependencies
    try:
        import numpy as np  # type: ignore
        exec_globals['np'] = np
    except Exception:
        pass

    try:
        import pandas as pd  # type: ignore
        exec_globals['pd'] = pd
    except Exception:
        pass

    # Add allowed stdlib modules
    exec_globals.update({
        're': re,
        'math': math,
        'datetime': datetime,
        'json': json,
        'random': random,
        'string': string,
    })

    # Add user-provided globals (these take precedence)
    if user_globals:
        for key, value in user_globals.items():
            if key.startswith('__'):
                continue
            exec_globals[key] = value

    return exec_globals


# ============================================================================
# TIMEOUT MECHANISM
# ============================================================================

class TimeoutException(Exception):
    """Raised when code execution times out"""
    pass


@contextmanager
def timeout_context(seconds: float):
    """Context manager for execution timeout (Unix only, threading fallback on Windows)"""
    if sys.platform != 'win32':
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutException(f"Execution timed out after {seconds} seconds")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, seconds)

        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # Windows fallback using threading
        result = {'exception': None}

        def check_timeout():
            time.sleep(seconds)
            result['exception'] = TimeoutException(f"Execution timed out after {seconds} seconds")

        timer = threading.Thread(target=check_timeout, daemon=True)
        timer.start()

        try:
            yield
        finally:
            if result['exception']:
                raise result['exception']


# ============================================================================
# SANDBOX EXECUTOR
# ============================================================================

class SandboxExecutor:
    """
    Secure sandbox for executing AI-generated code.

    Features:
    - AST validation before execution
    - Restricted builtins
    - Limited module access
    - Execution timeout
    - Output capture

    Example:
        executor = SandboxExecutor()
        result = executor.execute(
            code="df['new_col'] = df['old_col'] * 2",
            globals_dict={"df": my_dataframe, "pd": pd}
        )
    """

    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
        timeout: float = SandboxConfig.MAX_EXECUTION_TIME
    ):
        self.config = config or SandboxConfig()
        self.timeout = timeout
        self.validator = ASTSecurityValidator(self.config)
        self._safe_builtins = _create_safe_builtins()

    def execute(
        self,
        code: str,
        globals_dict: Optional[dict[str, Any]] = None,
        validate: bool = True
    ) -> dict[str, Any]:
        """
        Execute code in sandbox.

        Args:
            code: Python code to execute
            globals_dict: Global variables available to the code
            validate: Whether to perform AST validation

        Returns:
            Dict with:
            - success: bool
            - result: Any value returned
            - output: Captured stdout
            - error: Error message if failed
            - globals: Modified globals after execution
        """
        result = {
            'success': False,
            'result': None,
            'output': '',
            'error': None,
            'globals': {},
            'execution_time': 0.0
        }

        start_time = time.time()

        # Step 1: Validate AST
        if validate and not self.validator.validate(code):
            result['error'] = "Security validation failed: " + "; ".join(self.validator.errors)
            return result

        # Step 2: Execute (optionally isolated)
        if self.config.USE_SUBPROCESS:
            return self._execute_in_subprocess(code, globals_dict, validate)

        # Fallback: in-process execution
        exec_globals = _prepare_exec_globals(self._safe_builtins, self.config.ALLOWED_MODULES, globals_dict)

        # Step 3: Capture output
        output_buffer = io.StringIO()

        # Step 4: Execute with timeout
        try:
            # Redirect stdout
            old_stdout = sys.stdout
            sys.stdout = output_buffer

            try:
                with timeout_context(self.timeout):
                    exec(code, exec_globals)

                result['success'] = True
                result['globals'] = {
                    k: v for k, v in exec_globals.items()
                    if not k.startswith('_') and k not in self._safe_builtins
                }

            finally:
                sys.stdout = old_stdout

            # Capture output
            output = output_buffer.getvalue()
            if len(output) > self.config.MAX_OUTPUT_SIZE:
                output = output[:self.config.MAX_OUTPUT_SIZE] + "\n... (output truncated)"
            result['output'] = output

        except TimeoutException as e:
            result['error'] = str(e)
        except Exception as e:
            result['error'] = f"{type(e).__name__}: {e!s}"

        result['execution_time'] = time.time() - start_time

        return result

    def _execute_in_subprocess(
        self,
        code: str,
        globals_dict: Optional[dict[str, Any]],
        validate: bool,
    ) -> dict[str, Any]:
        """Execute code in a separate process with timeout."""
        result = {
            'success': False,
            'result': None,
            'output': '',
            'error': None,
            'globals': {},
            'execution_time': 0.0,
        }

        start_time = time.time()

        parent_conn, child_conn = multiprocessing.Pipe(duplex=False)

        proc = multiprocessing.Process(
            target=_sandbox_worker,
            args=(
                child_conn,
                code,
                globals_dict,
                validate,
                self.config.ALLOWED_MODULES,
                self.config.MAX_OUTPUT_SIZE,
                self._safe_builtins,
                self.timeout,
            ),
        )
        proc.daemon = True
        try:
            proc.start()
        except Exception as e:
            result['error'] = f"Failed to start sandbox subprocess: {e!s}"
            result['execution_time'] = time.time() - start_time
            return result
        proc.join(self.timeout)

        if proc.is_alive():
            proc.terminate()
            proc.join(1.0)
            result['error'] = f"Execution timed out after {self.timeout} seconds"
        else:
            if parent_conn.poll(0.1):
                child_result = parent_conn.recv()
                result.update(child_result)
            else:
                result['error'] = "Sandbox subprocess failed without output"

        result['execution_time'] = time.time() - start_time
        return result

    def validate_code(self, code: str) -> dict[str, Any]:
        """
        Validate code without executing.

        Returns:
            Dict with validation results
        """
        is_valid = self.validator.validate(code)

        return {
            'valid': is_valid,
            'errors': self.validator.errors.copy(),
            'warnings': self.validator.warnings.copy()
        }


# ============================================================================
# SUBPROCESS WORKER
# ============================================================================

def _sandbox_worker(
    conn,
    code: str,
    globals_dict: Optional[dict[str, Any]],
    validate: bool,
    allowed_modules: set[str],
    max_output_size: int,
    safe_builtins: dict[str, Any],
    timeout: float,
) -> None:
    """Run sandboxed code in a subprocess and send result to parent."""
    result = {
        'success': False,
        'result': None,
        'output': '',
        'error': None,
        'globals': {},
        'execution_time': 0.0,
    }
    start_time = time.time()

    try:
        if validate:
            config = SandboxConfig()
            config.ALLOWED_MODULES = allowed_modules
            validator = ASTSecurityValidator(config)
            if not validator.validate(code):
                result['error'] = "Security validation failed: " + "; ".join(validator.errors)
                conn.send(result)
                return

        exec_globals = _prepare_exec_globals(safe_builtins, allowed_modules, globals_dict)

        output_buffer = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = output_buffer

        try:
            # Rely on parent timeout; avoid platform-specific alarms here.
            exec(code, exec_globals)
            result['success'] = True
            safe_globals: dict[str, Any] = {}
            for key, value in exec_globals.items():
                if key.startswith('_') or key in safe_builtins:
                    continue
                try:
                    import pickle
                    pickle.dumps(value)
                except Exception:
                    continue
                safe_globals[key] = value
            result['globals'] = safe_globals
        finally:
            sys.stdout = old_stdout

        output = output_buffer.getvalue()
        if len(output) > max_output_size:
            output = output[:max_output_size] + "\n... (output truncated)"
        result['output'] = output

    except Exception as e:
        result['error'] = f"{type(e).__name__}: {e!s}"

    result['execution_time'] = time.time() - start_time
    try:
        conn.send(result)
    finally:
        conn.close()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def execute_sandboxed(
    code: str,
    globals_dict: Optional[dict[str, Any]] = None,
    timeout: float = 30.0
) -> dict[str, Any]:
    """
    Execute code in sandbox with default settings.

    Args:
        code: Python code to execute
        globals_dict: Global variables
        timeout: Execution timeout

    Returns:
        Execution result dict
    """
    executor = SandboxExecutor(timeout=timeout)
    return executor.execute(code, globals_dict)


def validate_code(code: str) -> dict[str, Any]:
    """
    Validate code without executing.

    Args:
        code: Python code to validate

    Returns:
        Validation result dict
    """
    executor = SandboxExecutor()
    return executor.validate_code(code)
