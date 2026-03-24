"""Deprecated provider module removed.

The active 1688 integration now uses `app.services.tmapi_1688_client.TMAPI1688Client`.
This placeholder remains only to make accidental stale imports fail with a clear message.
"""

raise ImportError(
    "app.services.onebound_1688_client has been removed. "
    "Use app.services.tmapi_1688_client.TMAPI1688Client instead."
)
