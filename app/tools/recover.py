"""When the connection drops after a request was sent, the server may have done it anyway. Repeating
the request blindly could add a dish twice, so look first."""

from collections.abc import Callable

from app.backend.errors import BackendUnavailable


def settle[T](first: Callable[[], T], *, landed: Callable[[], T | None]) -> T:
    """Run `first`. If it fails in a way that may still have gone through, ask `landed` whether its
    effect is there (it returns the result if so, else None) and only then run `first` once more.
    For a request that is safe to repeat, `landed` can return None. A second failure is raised."""
    try:
        return first()
    except BackendUnavailable as exc:
        if not exc.may_have_been_processed:
            raise
        return landed() or first()
