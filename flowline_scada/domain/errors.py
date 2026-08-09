"""Domain-specific exceptions.

Kept narrow and specific deliberately — the v1 review flagged broad
`except Exception` catching as a real source of hidden bugs (a caught
AttributeError from a typo gets logged as a generic "calculation failed"
instead of surfacing the actual programming error). Callers of this
package should be able to catch exactly what they mean to handle.
"""


class FlowlineError(Exception):
    """Base class for all domain-level errors raised by this package."""


class InvalidFluidError(FlowlineError):
    """Raised when a fluid name/identity isn't recognized by the backing
    property library, or a fluid definition is otherwise invalid."""


class PropertyEvaluationError(FlowlineError):
    """Raised when a fluid property can't be evaluated at the requested
    conditions — out-of-range inputs, a state outside the equation of
    state's validity envelope, non-convergence, etc."""


class NetworkError(FlowlineError):
    """Base class for pipeline-network topology errors."""


class DuplicateNodeError(NetworkError):
    """Raised when adding a node whose name is already in the network."""


class DuplicateEdgeError(NetworkError):
    """Raised when adding an edge whose name is already in the network."""


class UnknownNodeError(NetworkError):
    """Raised when referencing a node name the network doesn't contain."""


class UnknownEdgeError(NetworkError):
    """Raised when referencing an edge name the network doesn't contain."""


class DisconnectedNetworkError(NetworkError):
    """Raised when a network validity check finds nodes that can't be
    reached from the rest of the network — almost always a modeling
    mistake (a pipe that was never actually connected) rather than an
    intentional configuration."""
