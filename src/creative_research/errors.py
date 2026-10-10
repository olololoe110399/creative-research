"""Stable application error contract shared by CLI adapters."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    FAILED = 1
    USAGE = 2
    INTERRUPTED = 130


class ApplicationError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "operation_failed",
        hint: str = "",
        exit_code: ExitCode = ExitCode.FAILED,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.exit_code = exit_code
