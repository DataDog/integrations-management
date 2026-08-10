# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

def confirm_yes(prompt: str) -> bool:
    """Prompt the user for a yes/no answer, returning True if they just press enter."""
    suffix = " [Y/n] "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return True
    return answer in ("y", "yes")