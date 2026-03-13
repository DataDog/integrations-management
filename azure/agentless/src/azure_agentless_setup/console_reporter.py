# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Console-based progress reporting to stdout."""

import sys
from dataclasses import dataclass
from typing import NoReturn, Optional

from .errors import SetupError


@dataclass
class Step:
    """A setup step."""

    number: int
    total: int
    name: str
    step_id: str


class ConsoleReporter:
    """Reports progress to stdout with formatted output."""

    def __init__(self, total_steps: int):
        self.total_steps = total_steps
        self.current_step = 0
        self._current_step_id: Optional[str] = None

    def start_step(self, name: str, step_id: str) -> Step:
        self.current_step += 1
        self._current_step_id = step_id

        step = Step(
            number=self.current_step,
            total=self.total_steps,
            name=name,
            step_id=step_id,
        )

        print(f"\n[{step.number}/{step.total}] {step.name}...")

        return step

    def finish_step(self) -> None:
        pass

    def success(self, message: str) -> None:
        print(f"    ✓ {message}")

    def info(self, message: str) -> None:
        print(f"    ℹ {message}")

    def warning(self, message: str) -> None:
        print(f"    ⚠ {message}")

    def error(self, message: str, detail: Optional[str] = None) -> None:
        print(f"    ❌ {message}", file=sys.stderr)
        if detail:
            for line in detail.strip().split("\n"):
                print(f"       {line}", file=sys.stderr)

    def fatal(self, message: str, detail: Optional[str] = None) -> NoReturn:
        self.error(message, detail)
        raise SetupError(message, detail)

    def complete(self) -> None:
        print()
        print("=" * 60)
        print("✅ Agentless Scanner setup complete!")
        print("=" * 60)

    def summary(self, scanner_subscription: str, locations: list[str], subscriptions: list[str]) -> None:
        print()
        print("Deployment Summary:")
        print(f"  Scanner Subscription: {scanner_subscription}")
        if len(locations) == 1:
            print(f"  Location:             {locations[0]}")
        else:
            print(f"  Locations:            {len(locations)}")
            for loc in locations:
                print(f"    - {loc}")
        print(f"  Subscriptions:        {len(subscriptions)}")
        for s in subscriptions:
            marker = "(scanner)" if s == scanner_subscription else ""
            print(f"    - {s} {marker}")
