"""
Exceptions raised by this package.

Every error below is narrow and specific on purpose: catch exactly the
one you mean to handle, rather than a broad ``except Exception`` that
would also swallow real bugs (a typo, a wrong argument) behind a generic
message. All of them are subclasses of :class:`FlowlineError`, so catching
that is the way to handle "any domain error from this library" broadly
when that's genuinely what you want.

Example:

```python
from flowline_scada.domain.errors import FlowlineError, UnknownNodeError

try:
    network.get_node("nonexistent")
except UnknownNodeError:
    print("that node doesn't exist")
except FlowlineError:
    print("some other domain error occurred")
```
"""


class FlowlineError(Exception):
    """Base class for every error this package raises. Catch this to
    handle "any domain error" generically; catch one of its subclasses
    below to handle a specific failure precisely."""


class InvalidFluidError(FlowlineError):
    """A fluid name or definition isn't valid.

    Raised, for example, by :class:`~flowline_scada.domain.fluids.pure.PureFluid`
    when constructed with a fluid name the underlying property library
    doesn't recognize (a typo, or a fluid it simply doesn't support).
    """


class PropertyEvaluationError(FlowlineError):
    """A fluid property couldn't be computed at the requested conditions.

    Raised when a pressure/temperature (or composition) combination falls
    outside what the underlying property library can evaluate — usually
    an out-of-range input (e.g. a negative pressure) rather than a
    mistake in how the fluid itself was defined.
    """


class NetworkError(FlowlineError):
    """Base class for errors involving a
    :class:`~flowline_scada.domain.network.PipelineNetwork`'s topology."""


class DuplicateNodeError(NetworkError):
    """Raised by
    :meth:`~flowline_scada.domain.network.PipelineNetwork.add_node` when
    the network already has a node with that name."""


class DuplicateEdgeError(NetworkError):
    """Raised by
    :meth:`~flowline_scada.domain.network.PipelineNetwork.add_edge` when
    the network already has an edge with that name."""


class UnknownNodeError(NetworkError):
    """Raised when looking up a node name a
    :class:`~flowline_scada.domain.network.PipelineNetwork` doesn't
    contain — for example from
    :meth:`~flowline_scada.domain.network.PipelineNetwork.get_node`."""


class UnknownEdgeError(NetworkError):
    """Raised when looking up an edge name a
    :class:`~flowline_scada.domain.network.PipelineNetwork` doesn't
    contain — for example from
    :meth:`~flowline_scada.domain.network.PipelineNetwork.get_edge`."""


class DisconnectedNetworkError(NetworkError):
    """Raised by
    :meth:`~flowline_scada.domain.network.PipelineNetwork.validate` when
    some nodes can't be reached from the rest of the network. This is
    almost always a modeling mistake — a pipe that was meant to connect
    two parts of the network but never got added — rather than an
    intentional configuration, so it's treated as an error rather than a
    silently-accepted state."""


class ComponentError(FlowlineError):
    """Base class for errors involving a single physical component (a
    pipe, valve, leak, etc.), as opposed to overall network topology."""


class DuplicateLeakError(ComponentError):
    """Raised by :meth:`~flowline_scada.domain.components.Pipe.add_leak`
    when the pipe already has a leak with that name."""


class UnknownLeakError(ComponentError):
    """Raised when looking up a leak name a
    :class:`~flowline_scada.domain.components.Pipe` doesn't have — for
    example from :meth:`~flowline_scada.domain.components.Pipe.get_leak`."""
