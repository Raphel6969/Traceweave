"""Offline, deterministic security-log scenario generator.

The implementation lives in :mod:`datasets.generator.__main__` so invoking
``python -m datasets.generator`` does not import any runtime application code.
"""

__all__ = ["generate"]


def __getattr__(name: str):
    if name == "generate":
        from .__main__ import generate
        return generate
    raise AttributeError(name)
