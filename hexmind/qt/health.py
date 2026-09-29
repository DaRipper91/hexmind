"""Non-blocking health checks for configured Hexmind model CLIs."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from ..core import REGISTRY
from ..models import Model

# These are documented, read-only commands. Do not infer auth commands from a
# provider name or fall back to login/help commands.
AUTH_CHECKS: dict[str, tuple[str, ...]] = {
    "claude": ("auth", "status", "--json"),
    "codex": ("login", "status"),
    "opencode": ("auth", "list"),
}


@dataclass(frozen=True)
class HealthResult:
    name: str
    available: bool
    credential_ready: bool
    latency_ms: int
    credential_checked: bool = False
    credential_status: str = "not-checked"


class HealthScanner(QThread):
    """Scan local executable and credential prerequisites without running models."""

    finished = Signal(list)

    def scan(self) -> list[HealthResult]:
        results: list[HealthResult] = []
        for name, model in REGISTRY.models.items():
            started = time.perf_counter()
            available = bool(shutil.which(model.cli))
            credential_ready, credential_checked, credential_status = self._credential_status(
                model, available
            )
            results.append(
                HealthResult(
                    name=name,
                    available=available,
                    credential_ready=credential_ready,
                    latency_ms=self._latency(model.cli, available, model.verify, started),
                    credential_checked=credential_checked,
                    credential_status=credential_status,
                )
            )
        self.finished.emit(results)
        return results

    def run(self) -> None:
        self.scan()

    @staticmethod
    def _latency(cli: str, available: bool, verify: str, started: float) -> int:
        """Probe only executable startup; never send a model prompt from the health screen."""
        if not available or verify != "path":
            return -1
        try:
            subprocess.run(
                [cli, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return -1
        return round((time.perf_counter() - started) * 1000)

    @staticmethod
    def _credential_status(model: Model, available: bool) -> tuple[bool, bool, str]:
        """Check only declared credentials or an allowlisted read-only auth command.

        An unsupported provider is deliberately reported as ``not-checked`` rather
        than guessed from a login command, environment naming convention, or model
        invocation. That distinction keeps the health screen non-interactive.
        """
        if model.verify == "env":
            ready = bool(model.env and os.environ.get(model.env))
            return ready, True, "declared" if ready else "missing"
        if model.verify != "path" or not available:
            return True, False, "not-checked"

        args = AUTH_CHECKS.get(model.cli)
        if not args:
            return True, False, "not-checked"
        try:
            completed = subprocess.run(
                [model.cli, *args],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, True, "timeout"
        except (OSError, subprocess.SubprocessError):
            return False, True, "failed"
        return (completed.returncode == 0, True,
                "verified" if completed.returncode == 0 else "failed")


__all__ = ["AUTH_CHECKS", "HealthResult", "HealthScanner"]
