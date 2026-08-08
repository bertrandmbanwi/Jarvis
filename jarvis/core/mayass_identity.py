"""MayAss user-facing identity constants.

Phase 2 only defines identity labels. It does not route chat, invoke Hermes,
change voice behavior, or migrate memory.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MayAssChatLabels:
    empty_state: str
    assistant_label: str
    assistant_avatar: str
    user_label: str
    user_avatar: str
    streaming_placeholder: str
    processing_status: str


@dataclass(frozen=True)
class MayAssIdentity:
    display_name: str
    codename: str
    assistant_name: str
    assistant_short_name: str
    user_display_name: str
    greeting: str
    shutdown_line: str
    chat: MayAssChatLabels

    def user_facing_text(self) -> tuple[str, ...]:
        return (
            self.display_name,
            self.codename,
            self.assistant_name,
            self.assistant_short_name,
            self.user_display_name,
            self.greeting,
            self.shutdown_line,
            self.chat.empty_state,
            self.chat.assistant_label,
            self.chat.assistant_avatar,
            self.chat.user_label,
            self.chat.user_avatar,
            self.chat.streaming_placeholder,
            self.chat.processing_status,
        )


MAYASS_IDENTITY = MayAssIdentity(
    display_name="MayAss",
    codename="Maymint-Hermes",
    assistant_name="Maymint",
    assistant_short_name="มาย",
    user_display_name="บอส",
    greeting="มายพร้อมแล้วค่ะบอส",
    shutdown_line="มายพักระบบให้แล้วค่ะบอส",
    chat=MayAssChatLabels(
        empty_state="คุยกับมาย",
        assistant_label="Maymint",
        assistant_avatar="M",
        user_label="บอส",
        user_avatar="B",
        streaming_placeholder="มายกำลังคิด...",
        processing_status="มายกำลังคิด...",
    ),
)


def get_chat_labels() -> MayAssChatLabels:
    return MAYASS_IDENTITY.chat
