# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Progress reporting to stdout."""

import sys
from dataclasses import dataclass
from typing import Optional


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

    def fatal(self, message: str, detail: Optional[str] = None) -> None:
        """Report fatal error and exit."""
        self.error(message, detail)
        sys.exit(1)

    def complete(self) -> None:
        """Report setup complete."""
        print()
        print("=" * 60)
        print("✅ Agentless Scanner setup complete!")
        print("=" * 60)

    def summary(self, scanner_project: str, region: str, projects: list[str]) -> None:
        """Print deployment summary."""
        print()
        print("Deployment Summary:")
        print(f"  Scanner Project: {scanner_project}")
        print(f"  Region:          {region}")
        print(f"  Projects Scanned: {len(projects)}")
        for p in projects:
            marker = "(scanner)" if p == scanner_project else ""
            print(f"    - {p} {marker}")

