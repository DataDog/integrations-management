# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Progress reporting to stdout."""

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


class Reporter:
    """Reports progress to stdout."""

    def __init__(self, total_steps: int):
        self.total_steps = total_steps
        self.current_step = 0

    def start_step(self, name: str) -> Step:
        """Start a new step."""
        self.current_step += 1
        step = Step(number=self.current_step, total=self.total_steps, name=name)
        print(f"\n[{step.number}/{step.total}] {step.name}...")
        return step

    def success(self, message: str) -> None:
        """Report success for current step."""
        print(f"    ✓ {message}")

    def info(self, message: str) -> None:
        """Report info message."""
        print(f"    ℹ {message}")

    def warning(self, message: str) -> None:
        """Report warning message."""
        print(f"    ⚠ {message}")

    def error(self, message: str, detail: Optional[str] = None) -> None:
        """Report error message."""
        print(f"    ❌ {message}", file=sys.stderr)
        if detail:
            for line in detail.strip().split("\n"):
                print(f"       {line}", file=sys.stderr)

    def fatal(self, message: str, detail: Optional[str] = None) -> NoReturn:
        """Report fatal error and raise exception."""
        self.error(message, detail)
        raise SetupError(message, detail)

    def complete(self) -> None:
        """Report setup complete."""
        print()
        print("=" * 60)
        print("✅ Agentless Scanner setup complete!")
        print("=" * 60)

    def summary(self, scanner_project: str, regions: list[str], projects: list[str]) -> None:
        """Print deployment summary."""
        print()
        print("Deployment Summary:")
        print(f"  Scanner Project:  {scanner_project}")
        if len(regions) == 1:
            print(f"  Region:           {regions[0]}")
        else:
            print(f"  Regions:          {len(regions)}")
            for r in regions:
                print(f"    - {r}")
        print(f"  Projects Scanned: {len(projects)}")
        for p in projects:
            marker = "(scanner)" if p == scanner_project else ""
            print(f"    - {p} {marker}")
