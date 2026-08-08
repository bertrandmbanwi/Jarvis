"""Tests for the MayAss identity layer.

Phase 2 scope: define user-facing MayAss/Maymint identity without
routing chat, changing voice, or touching dashboard/cinematic surfaces.
"""


FORBIDDEN_VISIBLE_TOKENS = ("JARVIS", "J.A.R.V.I.S.", "Becs", "sir", "Forney")


def test_mayass_identity_uses_boss_and_may_names():
    from jarvis.core.mayass_identity import MAYASS_IDENTITY

    assert MAYASS_IDENTITY.display_name == "MayAss"
    assert MAYASS_IDENTITY.assistant_name == "Maymint"
    assert MAYASS_IDENTITY.assistant_short_name == "มาย"
    assert MAYASS_IDENTITY.user_display_name == "บอส"


def test_mayass_identity_user_facing_text_has_no_jarvis_persona_leakage():
    from jarvis.core.mayass_identity import MAYASS_IDENTITY

    visible_text = "\n".join(MAYASS_IDENTITY.user_facing_text())

    for token in FORBIDDEN_VISIBLE_TOKENS:
        assert token not in visible_text

    assert "มาย" in visible_text
    assert "บอส" in visible_text


def test_mayass_identity_exports_chat_labels():
    from jarvis.core.mayass_identity import get_chat_labels

    labels = get_chat_labels()

    assert labels.empty_state == "คุยกับมาย"
    assert labels.assistant_label == "Maymint"
    assert labels.assistant_avatar == "M"
    assert labels.user_label == "บอส"
    assert labels.user_avatar == "B"
    assert labels.streaming_placeholder == "มายกำลังคิด..."
    assert labels.processing_status == "มายกำลังคิด..."
