"""Runtime errors exposed by the local effect-generation agent."""

from __future__ import annotations


class AgentRuntimeError(RuntimeError):
    """Base class for expected runtime failures."""


class TaskNotFoundError(AgentRuntimeError):
    """Raised when a task state file does not exist."""


class TaskAlreadyExistsError(AgentRuntimeError):
    """Raised when creating a task whose state file already exists."""


class TaskLockTimeoutError(AgentRuntimeError):
    """Raised when another process holds a task lock for too long."""


class TaskValidationError(AgentRuntimeError):
    """Raised when task state does not satisfy the active JSON Schema."""


class InvalidTaskTransitionError(AgentRuntimeError):
    """Raised when a requested task or step transition is not allowed."""


class InputReferenceError(AgentRuntimeError):
    """Raised when a Step input reference cannot be resolved."""
