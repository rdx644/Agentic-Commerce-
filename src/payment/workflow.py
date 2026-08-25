"""
Durable checkout workflow — checkpointed, retryable, observable.

Models the checkout-to-payment flow as discrete, idempotent steps.
Each step is independently retryable with exponential backoff + jitter.
Non-retryable errors (guardrail rejection, token expired) short-circuit.

workflow-automation skill: durable execution patterns with
backoff, dead-letter, and checkpoint recovery.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.config import get_settings

logger = logging.getLogger(__name__)


class WorkflowStep(str, Enum):
    """Discrete steps in the checkout workflow."""
    VALIDATE_TOKEN = "validate_token"
    WRITE_PENDING = "write_pending_record"
    CALL_RAZORPAY = "call_razorpay"
    UPDATE_LEDGER = "update_ledger"
    COMPLETED = "completed"


class FailureType(str, Enum):
    """Classifies whether a failure is retryable."""
    RETRYABLE = "retryable"       # Network timeout, transient error
    NON_RETRYABLE = "non_retryable"  # Bad token, budget exceeded, validation error


@dataclass
class WorkflowState:
    """
    Tracks the current state of a checkout workflow.
    Acts as a checkpoint that can be persisted and resumed.
    """
    session_id: str
    current_step: WorkflowStep = WorkflowStep.VALIDATE_TOKEN
    completed_steps: list[str] = field(default_factory=list)
    attempt: int = 0
    max_attempts: int = 5
    last_error: Optional[str] = None
    last_failure_type: Optional[FailureType] = None
    razorpay_order_id: Optional[str] = None
    idempotency_key: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        """Check if workflow has reached a terminal state (success or max retries)."""
        return (
            self.current_step == WorkflowStep.COMPLETED
            or self.last_failure_type == FailureType.NON_RETRYABLE
            or self.attempt >= self.max_attempts
        )

    def mark_step_done(self, step: WorkflowStep) -> None:
        """Mark a step as completed and advance to next."""
        self.completed_steps.append(step.value)
        step_order = list(WorkflowStep)
        current_idx = step_order.index(step)
        if current_idx + 1 < len(step_order):
            self.current_step = step_order[current_idx + 1]

    def record_failure(self, error: str, failure_type: FailureType) -> None:
        """Record a failure and classify it."""
        self.last_error = error
        self.last_failure_type = failure_type
        self.attempt += 1


def compute_backoff_delay(attempt: int, base: float = 1.0, max_delay: float = 30.0) -> float:
    """
    Exponential backoff with full jitter.

    Formula: delay = random(0, min(base * 2^attempt, max_delay))

    Full jitter (vs equal jitter) provides better spread across
    concurrent retries, reducing thundering herd effects.
    """
    exponential = min(base * (2 ** attempt), max_delay)
    return random.uniform(0, exponential)


def should_retry(state: WorkflowState) -> bool:
    """
    Determine if a workflow step should be retried.

    Rules:
    - NEVER retry non-retryable failures (guardrail rejection, bad token)
    - Retry transient failures up to max_attempts
    - Respect backoff delay before each retry
    """
    if state.last_failure_type == FailureType.NON_RETRYABLE:
        logger.info(
            "Non-retryable failure for session=%s at step=%s: %s",
            state.session_id, state.current_step.value, state.last_error,
        )
        return False

    if state.attempt >= state.max_attempts:
        logger.warning(
            "Max retries (%d) exhausted for session=%s at step=%s",
            state.max_attempts, state.session_id, state.current_step.value,
        )
        return False

    return True


def execute_with_retry(
    fn,
    state: WorkflowState,
    step: WorkflowStep,
    *args,
    **kwargs,
):
    """
    Execute a workflow step with retry logic.

    - Calls fn(*args, **kwargs)
    - On transient failure: applies backoff, retries
    - On non-retryable failure: records and returns immediately
    - On success: marks step done in state
    """
    settings = get_settings()

    while not state.is_terminal and state.current_step == step:
        try:
            result = fn(*args, **kwargs)
            state.mark_step_done(step)
            logger.info(
                "Workflow step completed: session=%s, step=%s, attempt=%d",
                state.session_id, step.value, state.attempt,
            )
            return result

        except NonRetryableError as e:
            state.record_failure(str(e), FailureType.NON_RETRYABLE)
            logger.warning(
                "Non-retryable error in step %s: %s (session=%s)",
                step.value, e, state.session_id,
            )
            return None

        except RetryableError as e:
            state.record_failure(str(e), FailureType.RETRYABLE)
            if should_retry(state):
                delay = compute_backoff_delay(
                    state.attempt,
                    base=settings.retry_base_delay_seconds,
                    max_delay=settings.retry_max_delay_seconds,
                )
                logger.info(
                    "Retrying step %s in %.2fs (attempt %d/%d, session=%s): %s",
                    step.value, delay, state.attempt, state.max_attempts,
                    state.session_id, e,
                )
                time.sleep(delay)
            else:
                return None

        except Exception as e:
            # Unknown errors are treated as retryable (conservative)
            state.record_failure(str(e), FailureType.RETRYABLE)
            if should_retry(state):
                delay = compute_backoff_delay(
                    state.attempt,
                    base=settings.retry_base_delay_seconds,
                    max_delay=settings.retry_max_delay_seconds,
                )
                logger.warning(
                    "Unknown error in step %s, retrying in %.2fs: %s",
                    step.value, delay, e,
                )
                time.sleep(delay)
            else:
                return None

    return None


class RetryableError(Exception):
    """Raised for transient errors that can be retried (network timeout, etc)."""
    pass


class NonRetryableError(Exception):
    """Raised for permanent errors that should NOT be retried (bad token, budget exceeded)."""
    pass
