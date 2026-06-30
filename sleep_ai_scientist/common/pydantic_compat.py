from __future__ import annotations

from enum import Enum
from typing import Any

try:  # pragma: no cover - exercised when pydantic is installed.
    from pydantic import BaseModel, Field
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal runtime images.
    # The project declares pydantic as a dependency. This fallback only keeps the
    # Phase 1 CLI usable in restricted environments where dependencies have not
    # been installed yet; it implements the small subset used by our schemas.

    class _FieldInfo:
        def __init__(self, default: Any = None, default_factory: Any = None):
            self.default = default
            self.default_factory = default_factory

        def value(self) -> Any:
            if self.default_factory is not None:
                return self.default_factory()
            return self.default

    def Field(default: Any = None, default_factory: Any = None) -> _FieldInfo:
        return _FieldInfo(default=default, default_factory=default_factory)

    def _dump(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, BaseModel):
            return value.model_dump()
        if isinstance(value, list):
            return [_dump(item) for item in value]
        if isinstance(value, dict):
            return {key: _dump(item) for key, item in value.items()}
        return value

    class BaseModel:
        def __init__(self, **kwargs: Any):
            annotations = getattr(self.__class__, "__annotations__", {})
            for name in annotations:
                if name in kwargs:
                    value = kwargs[name]
                else:
                    class_value = getattr(self.__class__, name, None)
                    if isinstance(class_value, _FieldInfo):
                        value = class_value.value()
                    else:
                        value = class_value
                setattr(self, name, value)
            for name, value in kwargs.items():
                if name not in annotations:
                    setattr(self, name, value)

        def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {key: _dump(value) for key, value in self.__dict__.items()}
