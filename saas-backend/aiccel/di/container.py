# aiccel/di/container.py
"""
Dependency Injection Container
===============================

Lightweight DI container for managing dependencies.
Enables loose coupling and easy testing.

Usage:
    container = Container()
    container.register(LLMProtocol, GeminiProvider, api_key="...", model="...")
    container.register_singleton(ToolRegistry)

    provider = container.resolve(LLMProtocol)
"""

import inspect
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, get_type_hints


T = TypeVar('T')


class Lifetime(Enum):
    """Service lifetime."""
    TRANSIENT = "transient"    # New instance each time
    SINGLETON = "singleton"    # Single instance
    SCOPED = "scoped"          # Instance per scope


@dataclass
class Registration:
    """Service registration."""
    abstract_type: type
    concrete_type: type
    lifetime: Lifetime
    factory: Optional[Callable] = None
    kwargs: dict[str, Any] = None
    instance: Any = None  # For singletons


class Container:
    """
    Dependency Injection Container.

    Supports:
    - Constructor injection
    - Singleton and transient lifetimes
    - Factory functions
    - Scoped instances
    """

    def __init__(self, parent: Optional['Container'] = None):
        self._registrations: dict[type, Registration] = {}
        self._parent = parent
        self._scoped_instances: dict[type, Any] = {}

    def register(
        self,
        abstract: type[T],
        concrete: Optional[type[T]] = None,
        lifetime: Lifetime = Lifetime.TRANSIENT,
        factory: Optional[Callable[..., T]] = None,
        **kwargs
    ) -> 'Container':
        """
        Register a service.

        Args:
            abstract: Interface/protocol type
            concrete: Implementation type (optional if abstract is concrete)
            lifetime: Service lifetime
            factory: Factory function (optional)
            **kwargs: Constructor arguments
        """
        concrete = concrete or abstract

        self._registrations[abstract] = Registration(
            abstract_type=abstract,
            concrete_type=concrete,
            lifetime=lifetime,
            factory=factory,
            kwargs=kwargs or {}
        )

        return self

    def register_singleton(
        self,
        abstract: type[T],
        concrete: Optional[type[T]] = None,
        **kwargs
    ) -> 'Container':
        """Register as singleton."""
        return self.register(abstract, concrete, Lifetime.SINGLETON, **kwargs)

    def register_instance(self, abstract: type[T], instance: T) -> 'Container':
        """Register an existing instance."""
        self._registrations[abstract] = Registration(
            abstract_type=abstract,
            concrete_type=type(instance),
            lifetime=Lifetime.SINGLETON,
            instance=instance,
            kwargs={}
        )
        return self

    def register_factory(
        self,
        abstract: type[T],
        factory: Callable[..., T],
        lifetime: Lifetime = Lifetime.TRANSIENT
    ) -> 'Container':
        """Register with factory function."""
        return self.register(abstract, factory=factory, lifetime=lifetime)

    def resolve(self, abstract: type[T]) -> T:
        """
        Resolve a service.

        Args:
            abstract: Type to resolve

        Returns:
            Instance of the registered type
        """
        # Check local registrations
        if abstract in self._registrations:
            return self._create_instance(self._registrations[abstract])

        # Check parent
        if self._parent:
            return self._parent.resolve(abstract)

        # Try to auto-register concrete types
        if not inspect.isabstract(abstract) and not hasattr(abstract, '__protocol__'):
            self.register(abstract, abstract)
            return self._create_instance(self._registrations[abstract])

        raise KeyError(f"No registration found for {abstract.__name__}")

    def _create_instance(self, reg: Registration) -> Any:
        """Create instance based on registration."""

        # Return existing singleton instance
        if reg.lifetime == Lifetime.SINGLETON and reg.instance is not None:
            return reg.instance

        # Check scoped instances
        if reg.lifetime == Lifetime.SCOPED and reg.abstract_type in self._scoped_instances:
            return self._scoped_instances[reg.abstract_type]

        # Create new instance
        if reg.factory:
            instance = reg.factory(**reg.kwargs)
        else:
            # Auto-inject dependencies
            resolved_kwargs = self._resolve_dependencies(reg.concrete_type, reg.kwargs)
            instance = reg.concrete_type(**resolved_kwargs)

        # Store singleton
        if reg.lifetime == Lifetime.SINGLETON:
            reg.instance = instance

        # Store scoped
        if reg.lifetime == Lifetime.SCOPED:
            self._scoped_instances[reg.abstract_type] = instance

        return instance

    def _resolve_dependencies(self, cls: type, provided_kwargs: dict) -> dict[str, Any]:
        """Resolve constructor dependencies."""
        resolved = dict(provided_kwargs)

        try:
            hints = get_type_hints(cls.__init__)
        except Exception:
            return resolved

        sig = inspect.signature(cls.__init__)

        for param_name, param in sig.parameters.items():
            if param_name == 'self' or param_name in resolved:
                continue

            param_type = hints.get(param_name)

            if param_type and param_type in self._registrations:
                resolved[param_name] = self.resolve(param_type)
            elif param.default is not inspect.Parameter.empty:
                pass  # Has default, skip
            elif param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                pass  # *args, **kwargs, skip

        return resolved

    def create_scope(self) -> 'Container':
        """Create a scoped container."""
        return Container(parent=self)

    def has(self, abstract: type) -> bool:
        """Check if type is registered."""
        if abstract in self._registrations:
            return True
        if self._parent:
            return self._parent.has(abstract)
        return False


# ============================================================================
# DECORATORS
# ============================================================================

def injectable(cls: type[T]) -> type[T]:
    """Mark a class as injectable."""
    cls._injectable = True
    return cls


def inject(**dependencies):
    """
    Decorator to inject dependencies into a function.

    Usage:
        @inject(provider=LLMProtocol, tools=ToolRegistry)
        def my_function(query: str, provider: LLMProtocol, tools: ToolRegistry):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, container: Container = None, **kwargs):
            if container:
                for name, dep_type in dependencies.items():
                    if name not in kwargs:
                        kwargs[name] = container.resolve(dep_type)
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# GLOBAL CONTAINER
# ============================================================================

_global_container: Optional[Container] = None


def get_container() -> Container:
    """Get the global container."""
    global _global_container
    if _global_container is None:
        _global_container = Container()
    return _global_container


def configure_container(setup_func: Callable[[Container], None]) -> Container:
    """Configure the global container."""
    container = get_container()
    setup_func(container)
    return container
