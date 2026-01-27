# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Progress display for Terraform apply with emoji progress bar."""

import re
import subprocess
import sys
from collections import deque
from typing import Optional


# Number of recent Terraform output lines to display
PROGRESS_DISPLAY_LINES = 5

# Maximum line length before truncation (0 = no truncation)
PROGRESS_LINE_MAX_LENGTH = 0

# Emoji for progress bar
EMOJI_COMPLETE = "🟩"
EMOJI_PENDING = "⬜"

# Progress bar width (number of emoji)
PROGRESS_BAR_WIDTH = 20

# ANSI color codes
COLOR_GRAY = "\033[37m"  # Light gray
COLOR_RESET = "\033[0m"

# Regex to strip ANSI escape codes
ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*m')


def is_tty() -> bool:
    """Check if stdout is a TTY (supports ANSI escape codes)."""
    return sys.stdout.isatty()


def move_cursor_up(lines: int) -> None:
    """Move cursor up N lines."""
    if lines > 0:
        sys.stdout.write(f"\033[{lines}A")


def clear_line() -> None:
    """Clear the current line."""
    sys.stdout.write("\033[2K\r")


def clear_lines(count: int) -> None:
    """Clear N lines starting from current position going up."""
    for _ in range(count):
        clear_line()
        move_cursor_up(1)
    clear_line()


def build_progress_bar(completed: int, total: int) -> str:
    """Build an emoji progress bar string.
    
    Args:
        completed: Number of completed resources.
        total: Total number of resources.
    
    Returns:
        Formatted progress bar string.
    """
    if total == 0:
        return f"  {EMOJI_PENDING * PROGRESS_BAR_WIDTH}  0/0 resources"
    
    percentage = min(completed / total, 1.0)
    filled = int(percentage * PROGRESS_BAR_WIDTH)
    empty = PROGRESS_BAR_WIDTH - filled
    
    bar = EMOJI_COMPLETE * filled + EMOJI_PENDING * empty
    percent_str = f"{int(percentage * 100)}%"
    
    return f"  {bar}  {percent_str}  {completed}/{total} resources"


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return ANSI_ESCAPE_PATTERN.sub('', text)


def parse_plan_total(line: str) -> Optional[int]:
    """Parse the total number of resources from terraform plan output.
    
    Looks for: "Plan: X to add, Y to change, Z to destroy."
    
    Returns:
        Total resources to add, or None if not found.
    """
    # Strip ANSI codes before parsing
    clean_line = strip_ansi(line)
    match = re.search(r"Plan: (\d+) to add", clean_line)
    if match:
        return int(match.group(1))
    return None


def is_plan_line(line: str) -> bool:
    """Check if this is the plan summary line."""
    clean_line = strip_ansi(line)
    return "Plan:" in clean_line and "to add" in clean_line


def is_resource_complete(line: str) -> bool:
    """Check if a line indicates a resource creation completed."""
    clean_line = strip_ansi(line)
    return "Creation complete" in clean_line or "Still creating" in clean_line


def is_resource_created(line: str) -> bool:
    """Check if a line indicates a resource was successfully created."""
    clean_line = strip_ansi(line)
    return "Creation complete" in clean_line


class TerraformProgressDisplay:
    """Displays Terraform apply progress with emoji progress bar.
    
    Has two phases:
    1. Plan phase: Shows all output until the "Plan:" line
    2. Apply phase: Shows rolling progress with progress bar
    """
    
    def __init__(self):
        self.recent_lines: deque = deque(maxlen=PROGRESS_DISPLAY_LINES)
        self.total_resources: int = 0
        self.completed_resources: int = 0
        self.use_tty: bool = is_tty()
        self.lines_displayed: int = 0
        self.in_apply_phase: bool = False  # Start in plan phase
    
    def _redraw(self) -> None:
        """Redraw the progress display."""
        if not self.use_tty:
            return
        
        # Move cursor up to overwrite previous display
        if self.lines_displayed > 0:
            move_cursor_up(self.lines_displayed)
        
        # Clear and redraw each line
        lines_to_draw: list[str] = []
        
        # Add recent terraform output lines (in gray)
        for line in self.recent_lines:
            lines_to_draw.append(f"  {COLOR_GRAY}{line}{COLOR_RESET}")
        
        # Pad with empty lines if we don't have enough
        while len(lines_to_draw) < PROGRESS_DISPLAY_LINES:
            lines_to_draw.append("")
        
        # Add progress bar (normal color)
        lines_to_draw.append("")
        lines_to_draw.append(build_progress_bar(self.completed_resources, self.total_resources))
        
        # Draw all lines
        for line in lines_to_draw:
            clear_line()
            print(line)
        
        sys.stdout.flush()
        self.lines_displayed = len(lines_to_draw)
    
    def process_line(self, line: str) -> None:
        """Process a line of Terraform output.
        
        Args:
            line: A line from terraform apply output.
        """
        line = line.strip()
        if not line:
            return
        
        # Check for plan total - this triggers switch to apply phase
        total = parse_plan_total(line)
        if total is not None:
            self.total_resources = total
            # Print the plan line, then switch to apply phase
            print(f"  {line}")
            print()  # Empty line before progress display
            self.in_apply_phase = True
            return
        
        # Plan phase: print all output directly
        if not self.in_apply_phase:
            print(f"  {line}")
            return
        
        # Apply phase: use progress display
        # Check for resource completion
        if is_resource_created(line):
            self.completed_resources += 1
        
        # Add to recent lines (filter out noisy lines)
        if self._should_display_line(line):
            self.recent_lines.append(self._truncate_line(strip_ansi(line)))
        
        # Redraw if TTY, otherwise just print
        if self.use_tty:
            self._redraw()
        else:
            # Simple fallback: just print the line
            print(f"  {line}")
    
    def _should_display_line(self, line: str) -> bool:
        """Check if a line should be displayed in the progress view."""
        clean_line = strip_ansi(line)
        # Skip empty lines and some noisy terraform output
        skip_patterns = [
            "Terraform will perform",
            "Terraform used the selected",
            "Unless you have made equivalent",
            "This plan was saved to",
            "To perform exactly these",
            "─────────────────",
            "Apply complete!",
        ]
        return not any(pattern in clean_line for pattern in skip_patterns)
    
    def _truncate_line(self, line: str) -> str:
        """Truncate a line if it's too long."""
        if PROGRESS_LINE_MAX_LENGTH == 0:
            return line
        if len(line) <= PROGRESS_LINE_MAX_LENGTH:
            return line
        return line[:PROGRESS_LINE_MAX_LENGTH - 3] + "..."
    
    def finish(self) -> None:
        """Finish the progress display and show final state."""
        if self.use_tty and self.in_apply_phase:
            # Final redraw with completion
            self._redraw()
            print()  # Add newline after progress bar


def run_terraform_with_progress(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a terraform command with progress display.
    
    Args:
        cmd: The terraform command to run.
    
    Returns:
        CompletedProcess with return code.
    """
    display = TerraformProgressDisplay()
    
    # Start the process with piped output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffered
    )
    
    # Process output line by line
    all_output: list[str] = []
    for line in iter(process.stdout.readline, ""):
        all_output.append(line)
        display.process_line(line)
    
    process.wait()
    display.finish()
    
    return subprocess.CompletedProcess(
        args=cmd,
        returncode=process.returncode,
        stdout="".join(all_output),
        stderr="",
    )

