"""Cost tracker — estimates kWh and equivalent USD for local agent inference.

Local models don't cost API dollars but they DO cost electricity, GPU wear,
and developer time. This module estimates per-turn cost based on:
  - Quantization tier (bigger quant = more compute = more energy)
  - Inference time
  - GPU TDP (assumed RTX 4090: 450W peak)
  - Local power rate (default $0.15/kWh — configurable)

Per-session and daily totals are persisted to ~/.gemi/costs.json so users
can see cumulative cost across sessions.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

COSTS_FILE = Path.home() / ".gemi" / "costs.json"

# GPU TDP under inference load (most are around 60-70% of peak rated)
DEFAULT_GPU_WATTS = 350  # RTX 4090 sustained inference

# Energy multiplier per quant — denser quants do more compute per token
QUANT_ENERGY_MULTIPLIER: dict[str, float] = {
    "Q2_K_P": 0.55,
    "IQ3_M":  0.65,
    "Q3_K_M": 0.70,
    "Q4_K_M": 0.85,
    "Q5_K_M": 1.00,  # baseline
    "Q6_K_P": 1.15,
    "Q8_0":   1.45,
    "Q8_K_P": 1.50,
    "F16":    2.00,
    "F32":    3.50,
}


@dataclass
class TurnCost:
    agent: str = ""
    quant: str = ""
    elapsed: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    kwh: float = 0.0
    usd: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class SessionCost:
    agent: str = ""
    started: float = field(default_factory=time.time)
    turns: int = 0
    total_kwh: float = 0.0
    total_usd: float = 0.0
    total_input: int = 0
    total_output: int = 0
    total_seconds: float = 0.0


@dataclass
class CostConfig:
    gpu_watts: float = DEFAULT_GPU_WATTS
    rate_usd_per_kwh: float = 0.15
    cpu_overhead_watts: float = 50.0  # rest of system

    @property
    def total_watts(self) -> float:
        return self.gpu_watts + self.cpu_overhead_watts


def estimate_turn_cost(
    quant: str,
    elapsed: float,
    config: CostConfig | None = None,
) -> tuple[float, float]:
    """Returns (kwh, usd) for a single turn."""
    cfg = config or CostConfig()
    multiplier = QUANT_ENERGY_MULTIPLIER.get(quant, 1.0)
    effective_watts = cfg.total_watts * multiplier
    hours = elapsed / 3600.0
    kwh = (effective_watts / 1000.0) * hours
    usd = kwh * cfg.rate_usd_per_kwh
    return kwh, usd


def _load_persisted() -> dict[str, Any]:
    if not COSTS_FILE.exists():
        return {"daily": {}, "by_agent": {}, "lifetime": {"kwh": 0.0, "usd": 0.0, "turns": 0}}
    try:
        return json.loads(COSTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"daily": {}, "by_agent": {}, "lifetime": {"kwh": 0.0, "usd": 0.0, "turns": 0}}


def _save_persisted(data: dict[str, Any]) -> None:
    COSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COSTS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


class CostTracker:
    def __init__(self, config: CostConfig | None = None):
        self.config = config or CostConfig()
        self.session = SessionCost()
        self.recent: list[TurnCost] = []
        self.recent_max = 100

    def record(
        self,
        agent_slug: str,
        quant: str,
        elapsed: float,
        input_tokens: int,
        output_tokens: int,
    ) -> TurnCost:
        kwh, usd = estimate_turn_cost(quant, elapsed, self.config)
        turn = TurnCost(
            agent=agent_slug, quant=quant, elapsed=elapsed,
            input_tokens=input_tokens, output_tokens=output_tokens,
            kwh=kwh, usd=usd,
        )
        self.session.agent = agent_slug
        self.session.turns += 1
        self.session.total_kwh += kwh
        self.session.total_usd += usd
        self.session.total_input += input_tokens
        self.session.total_output += output_tokens
        self.session.total_seconds += elapsed
        self.recent.append(turn)
        if len(self.recent) > self.recent_max:
            del self.recent[: len(self.recent) - self.recent_max]
        self._persist(turn)
        return turn

    def _persist(self, turn: TurnCost) -> None:
        data = _load_persisted()
        today = time.strftime("%Y-%m-%d")
        day = data["daily"].setdefault(today, {"kwh": 0.0, "usd": 0.0, "turns": 0, "seconds": 0.0})
        day["kwh"] += turn.kwh
        day["usd"] += turn.usd
        day["turns"] += 1
        day["seconds"] += turn.elapsed

        agent_stats = data["by_agent"].setdefault(turn.agent, {"kwh": 0.0, "usd": 0.0, "turns": 0, "seconds": 0.0})
        agent_stats["kwh"] += turn.kwh
        agent_stats["usd"] += turn.usd
        agent_stats["turns"] += 1
        agent_stats["seconds"] += turn.elapsed

        lifetime = data["lifetime"]
        lifetime["kwh"] += turn.kwh
        lifetime["usd"] += turn.usd
        lifetime["turns"] += 1
        try:
            _save_persisted(data)
        except Exception:
            pass

    def get_lifetime(self) -> dict[str, Any]:
        return _load_persisted()


_DEFAULT: CostTracker | None = None


def get_tracker() -> CostTracker:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = CostTracker()
    return _DEFAULT
