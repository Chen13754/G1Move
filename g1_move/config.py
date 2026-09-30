"""Small, project-local configuration for time-based motion."""

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


def number(value, name: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or result < 0 or (result == 0 and not allow_zero):
        raise ValueError(f"{name} must be finite and {'>= 0' if allow_zero else '> 0'}")
    return result


@dataclass(frozen=True)
class MotionConfig:
    linear_speed_mps: float = 0.2
    angular_speed_deg_s: float = 15.0
    move_time_factors: Mapping[str, float] = field(default_factory=lambda: {
        "forward": 1.2048192771084338, "backward": 1.3693181818181819,
        "left": 1.8382352941176467, "right": 1.2254666666666667,
    })
    turn_time_factors: Mapping[str, float] = field(default_factory=lambda: {
        "left": 1.62, "right": 1.62,
    })
    pause_s: float = 0.5
    rpc_timeout_s: float = 2.0

    def __post_init__(self):
        for name in ("linear_speed_mps", "angular_speed_deg_s", "pause_s", "rpc_timeout_s"):
            object.__setattr__(self, name, number(getattr(self, name), name, allow_zero=name == "pause_s"))
        for name, directions in (
            ("move_time_factors", {"forward", "backward", "left", "right"}),
            ("turn_time_factors", {"left", "right"}),
        ):
            factors = getattr(self, name)
            if not isinstance(factors, Mapping) or set(factors) != directions:
                raise ValueError(f"{name} must contain exactly {sorted(directions)}")
            object.__setattr__(self, name, MappingProxyType({
                key: number(value, f"{name}.{key}") for key, value in factors.items()
            }))

    @classmethod
    def from_file(cls, path: str | Path) -> "MotionConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a JSON object")
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
        return cls(**data)
