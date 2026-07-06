"""Server-side confirmation for high-risk tool calls.

The permission gate must not trust a ``confirmed`` flag supplied by the model:
a prompt-injected model could set it itself and bypass the human-in-the-loop
check. Instead, confirmation is granted here by *trusted server code* — a future
UI approval endpoint, or the voice loop after hearing a spoken "yes" from the
physically-present user — by running the tool inside ``confirmed_scope()``.

The grant is stored in a ContextVar so it is scoped to the current async task
and cannot leak across concurrent requests.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_confirmed: ContextVar[bool] = ContextVar("jarvis_action_confirmed", default=False)


def is_confirmed() -> bool:
    """Return whether the current task is executing under a server-granted confirmation."""
    return _confirmed.get()


@contextmanager
def confirmed_scope() -> Iterator[None]:
    """Grant confirmation for high-risk tool calls made within this scope.

    Only trusted server code should call this — never a path whose arguments the
    model controls.
    """
    token = _confirmed.set(True)
    try:
        yield
    finally:
        _confirmed.reset(token)
