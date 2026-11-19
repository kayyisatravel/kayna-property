"""Helpers for reliable, data-bound user review confirmations in Streamlit forms."""
from __future__ import annotations
from typing import MutableMapping, Any


def sync_review_confirmation(
    state: MutableMapping[str, Any],
    value_key: str,
    signature_key: str,
    current_signature: str,
) -> None:
    """Keep a review checkbox stable across reruns and reset it only on data changes.

    On first render, initialize the fingerprint without overwriting an existing
    saved confirmation. On later renders, a changed fingerprint invalidates the
    previous confirmation. Merely clicking the checkbox does not change the data
    fingerprint, so the user's new True value survives the next Streamlit rerun.
    """
    previous_signature = state.get(signature_key)
    if previous_signature is None:
        state[signature_key] = current_signature
        state.setdefault(value_key, False)
        return

    if previous_signature != current_signature:
        state[signature_key] = current_signature
        state[value_key] = False
    else:
        state.setdefault(value_key, False)
