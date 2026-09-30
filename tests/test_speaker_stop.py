"""stop_speaking must end only JARVIS's own playback processes."""

import asyncio
import sys

import pytest

from jarvis.voice.speaker import VoiceSpeaker


@pytest.mark.asyncio
async def test_stop_speaking_terminates_only_tracked_playback():
    speaker = VoiceSpeaker()
    other = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(5)")
    playback = asyncio.create_task(speaker._run_playback(sys.executable, "-c", "import time; time.sleep(5)"))
    for _ in range(100):
        if speaker._playback_procs:
            break
        await asyncio.sleep(0.01)

    speaker.stop_speaking()
    await asyncio.wait_for(playback, timeout=3)

    assert not speaker._playback_procs
    assert other.returncode is None  # unrelated process untouched
    other.kill()
    await other.wait()
