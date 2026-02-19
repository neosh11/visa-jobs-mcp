from __future__ import annotations

from contextlib import contextmanager
from inspect import isfunction
from types import FunctionType, ModuleType
from typing import Any

from visa_jobs_mcp import __version__ as __package_version
from .server_parts import base as _base
from .server_parts import tools_core as _tools_core
from .server_parts import tools_jobs_core as _tools_jobs_core
from .server_parts import tools_jobs_data as _tools_jobs_data
from .server_parts import tools_search as _tools_search

__version__ = __package_version


def _rebind_function(func: FunctionType) -> FunctionType:
    wrapped = getattr(func, "__wrapped__", None)
    if isinstance(wrapped, FunctionType) and "server_parts" in wrapped.__code__.co_filename:
        rebound_wrapped = _rebind_function(wrapped)
        rebuilt = contextmanager(rebound_wrapped)
        rebuilt.__module__ = __name__
        return rebuilt

    if "server_parts" not in func.__code__.co_filename:
        return func

    rebound = FunctionType(
        func.__code__,
        globals(),
        name=func.__name__,
        argdefs=func.__defaults__,
        closure=func.__closure__,
    )
    rebound.__kwdefaults__ = func.__kwdefaults__
    rebound.__annotations__ = dict(getattr(func, "__annotations__", {}))
    rebound.__doc__ = func.__doc__
    rebound.__module__ = __name__
    return rebound


def _export_module_symbols(module: ModuleType, include_private_functions: bool = True) -> None:
    for name, value in module.__dict__.items():
        if name.startswith("__"):
            continue
        if isfunction(value):
            if name.startswith("_") and not include_private_functions:
                continue
            globals()[name] = _rebind_function(value)
        else:
            globals()[name] = value


_export_module_symbols(_base, include_private_functions=True)
_export_module_symbols(_tools_core, include_private_functions=False)
_export_module_symbols(_tools_jobs_core, include_private_functions=False)
_export_module_symbols(_tools_jobs_data, include_private_functions=False)
_export_module_symbols(_tools_search, include_private_functions=False)


def main() -> None:
    _disable_proxies()
    _ensure_job_management_ready()
    mcp.run()


if __name__ == "__main__":
    main()
