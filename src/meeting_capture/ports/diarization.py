"""DiarizationPort: speaker attribution (slice 2), re-exported from the shared speech kit.

Diarization is a separate port from recognition on purpose: stereo contact-centre capture knows
its channels from telephony configuration, whereas a meeting is single-channel and the speakers
are resolved from the audio. The domain joins the two deterministically with the kit's
``merge_diarization`` (see ``domain/turns.py``), so the same audio yields the same speaker labels
on every replay.
"""

from __future__ import annotations

from speech_lexicon_kit import (
    DiarizationPort,
    DiarizationRequest,
    DiarizationResult,
    SpeakerSegment,
)

__all__ = [
    "DiarizationPort",
    "DiarizationRequest",
    "DiarizationResult",
    "SpeakerSegment",
]
