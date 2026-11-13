"""Normalize policy references without depending on backend policy rule types."""

from collections.abc import Sequence
from uuid import UUID
from warnings import warn

from contree_client.models import InstanceNetworking


def apply_legacy_networking(
    networking: InstanceNetworking | None,
    network_enabled: bool | None,
    network_policy: str | Sequence[str] | None,
) -> tuple[bool | None, str | Sequence[str] | None]:
    if networking is None:
        return network_enabled, network_policy
    if network_enabled is not None or network_policy is not None:
        raise ValueError("networking cannot be combined with network_enabled or network_policy")

    # Backward compatibility workaround for the deprecated networking argument on run()/spawn().
    warn("networking is deprecated; use network_enabled and network_policy instead", DeprecationWarning, stacklevel=3)
    enabled = True if networking.enabled is ... else networking.enabled
    policy = () if networking.policy is ... else networking.policy
    return enabled, policy


def validate_policy_references(policy: str | Sequence[str] | None) -> tuple[str, ...]:
    """Copy and validate UUID/tag inputs before lookup or a VM lifecycle change.

    Returns:
        References as a tuple; None and an empty sequence produce an empty tuple.

    Raises:
        TypeError: The input is not a string or a sequence of strings.
        ValueError: A reference is empty or is neither a UUID nor tag:name.

    """
    if policy is None:
        return ()
    if isinstance(policy, str):
        references = (policy,)
    elif isinstance(policy, Sequence) and not isinstance(policy, (bytes, bytearray)):
        references = tuple(policy)
    else:
        raise TypeError("network policy must be a UUID/tag string, a sequence of strings, or None")

    for reference in references:
        if not isinstance(reference, str):
            raise TypeError("network policy references must be strings")
        if not reference.removeprefix("tag:").strip():
            raise ValueError("network policy references must not be empty")
        if not reference.startswith("tag:"):
            validate_policy_uuid(reference)
    return references


def validate_policy_uuid(reference: str) -> str:
    """Validate and normalize a policy UUID.

    Returns:
        A canonical UUID.

    Raises:
        ValueError: The reference is not a UUID.

    """
    try:
        return str(UUID(reference))
    except ValueError as error:
        raise ValueError("network policy reference must be a UUID") from error


def validate_network_enabled(enabled: bool) -> bool:
    if not isinstance(enabled, bool):
        raise TypeError("network enabled must be a bool")
    return enabled
