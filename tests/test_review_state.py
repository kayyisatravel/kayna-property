from core.review_state import sync_review_confirmation


def test_first_render_initializes_signature_and_default_without_erasing_saved_value():
    state = {"reviewed": True}
    sync_review_confirmation(state, "reviewed", "signature", "abc")
    assert state["reviewed"] is True
    assert state["signature"] == "abc"


def test_checkbox_value_survives_rerun_when_data_signature_is_unchanged():
    state = {"reviewed": False, "signature": "abc"}
    state["reviewed"] = True  # Streamlit checkbox interaction before rerun
    sync_review_confirmation(state, "reviewed", "signature", "abc")
    assert state["reviewed"] is True


def test_changed_data_resets_previous_confirmation():
    state = {"reviewed": True, "signature": "before"}
    sync_review_confirmation(state, "reviewed", "signature", "after")
    assert state["reviewed"] is False
    assert state["signature"] == "after"
