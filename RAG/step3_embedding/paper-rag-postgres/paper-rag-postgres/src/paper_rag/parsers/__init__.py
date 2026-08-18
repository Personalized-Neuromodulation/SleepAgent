from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .registry import ParserRegistry

__all__ = ["ParserRegistry"]


def __getattr__(name: str):
    if name == "ParserRegistry":
        from .registry import ParserRegistry

        return ParserRegistry
    raise AttributeError(name)
