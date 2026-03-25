"""JARVIS Voice Speaker: text-to-speech output using Kokoro TTS, Piper, or Edge TTS."""
import asyncio
import base64
import logging
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Callable, Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.voice.speaker")

try:
    import kokoro
    HAS_KOKORO = True
except ImportError:
    HAS_KOKORO = False

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False


class VoiceSpeaker:
    """Text-to-speech with fallback support: Kokoro TTS, Edge TTS, or macOS 'say'."""

    def __init__(self):
        self._engine = None
        self._backend = None
        self._kokoro_pipeline = None
        self._last_amplitude_envelope: list[float] = []
        self._last_audio_duration: float = 0.0

    def initialize(self) -> bool:
        """Initialize the best available TTS engine."""
        if HAS_KOKORO and settings.TTS_ENGINE in ("kokoro", "auto"):
            try:
                # Derive lang_code from voice ID prefix (af_*/am_* = American (a), bf_*/bm_* = British (b), etc.)
                lang_code = getattr(settings, "TTS_LANG_CODE", None)
                if not lang_code:
                    voice_prefix = settings.TTS_VOICE[:1] if settings.TTS_VOICE else "a"
                    lang_code = voice_prefix if voice_prefix in ("a", "b", "j", "z", "e", "f", "h", "i", "p") else "a"
                self._kokoro_pipeline = kokoro.KPipeline(lang_code=lang_code)
                self._backend = "kokoro"
                logger.info(
                    "Kokoro TTS initialized (voice: %s, lang: %s)",
                    settings.TTS_VOICE, lang_code,
                )
                return True
            except Exception as e:
                logger.warning("Kokoro TTS init failed: %s", e)

        if HAS_EDGE_TTS and settings.TTS_ENGINE in ("edge", "auto"):
            self._backend = "edge"
            logger.info("Edge TTS initialized.")
            return True

        if self._check_macos_say():
            self._backend = "macos_say"
            logger.info("Using macOS 'say' command for TTS.")
            return True

        logger.error("No TTS engine available.")
        return False

    def _check_macos_say(self) -> bool:
        """Check if macOS 'say' command is available."""
        try:
            result = subprocess.run(["which", "say"], capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _fix_pronunciation(text: str) -> str:
        """Fix words and acronyms that TTS engines mispronounce."""
        import re

        pronunciation_map = {
            "JARVIS": "Jarvis",
            "J.A.R.V.I.S.": "Jarvis",
            "J.A.R.V.I.S": "Jarvis",
            "AI": "A.I.",  # Keep as initialism
            "API": "A.P.I.",
            "URL": "U.R.L.",
            "LLM": "L.L.M.",
            "TTS": "T.T.S.",
            "STT": "S.T.T.",
            "macOS": "mac O.S.",
            "iOS": "i O.S.",
            "CPU": "C.P.U.",
            "GPU": "G.P.U.",
            "RAM": "ram",
            "SSD": "S.S.D.",
            "USB": "U.S.B.",
            "HTTP": "H.T.T.P.",
            "HTTPS": "H.T.T.P.S.",
            "DNS": "D.N.S.",
            "SSH": "S.S.H.",
            "CLI": "C.L.I.",
            "GB": "gigabytes",
            "MB": "megabytes",
            "TB": "terabytes",
            "GHz": "gigahertz",
            "MHz": "megahertz",
        }

        for original, replacement in pronunciation_map.items():
            text = re.sub(
                r'\b' + re.escape(original) + r'\b',
                replacement,
                text
            )

        return text

    @staticmethod
    def _naturalize_text(text: str) -> str:
        """Preprocess text for natural TTS output: contractions, markdown cleanup, dash/ellipsis fixes."""
        import re

        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

        # Replace em/en dashes and ellipses that cause awkward TTS pauses
        text = text.replace('\u2014', ', ')
        text = text.replace('\u2013', ' to ')
        text = text.replace('--', ', ')
        text = text.replace('...', '.')
        text = text.replace('\u2026', '.')

        contractions = {
            "I am": "I'm",
            "I have": "I've",
            "I will": "I'll",
            "I would": "I'd",
            "it is": "it's",
            "it has": "it's",
            "it will": "it'll",
            "that is": "that's",
            "that has": "that's",
            "there is": "there's",
            "there are": "there're",
            "here is": "here's",
            "what is": "what's",
            "who is": "who's",
            "how is": "how's",
            "where is": "where's",
            "when is": "when's",
            "why is": "why's",
            "do not": "don't",
            "does not": "doesn't",
            "did not": "didn't",
            "is not": "isn't",
            "are not": "aren't",
            "was not": "wasn't",
            "were not": "weren't",
            "will not": "won't",
            "would not": "wouldn't",
            "could not": "couldn't",
            "should not": "shouldn't",
            "cannot": "can't",
            "can not": "can't",
            "have not": "haven't",
            "has not": "hasn't",
            "had not": "hadn't",
            "you are": "you're",
            "you have": "you've",
            "you will": "you'll",
            "we are": "we're",
            "we have": "we've",
            "we will": "we'll",
            "they are": "they're",
            "they have": "they've",
            "they will": "they'll",
            "let us": "let's",
        }

        for formal, contracted in contractions.items():
            pattern = re.compile(re.escape(formal), re.IGNORECASE)
            text = pattern.sub(contracted, text)

        text = re.sub(r'\n+', '. ', text)
        text = re.sub(r'\s{2,}', ' ', text)
        text = text.replace('*', '')
        text = text.replace('#', '')
        text = text.replace('_', ' ')

        return text.strip()

    async def speak(
        self,
        text: str,
        on_audio_ready: "Callable | None" = None,
        on_audio_chunk: "Callable | None" = None,
        skip_local_playback: bool = False,
    ):
        """Convert text to speech and play it; optionally stream chunks for faster UI response."""
        if not text or not text.strip():
            return

        text = text.strip()
        text = self._naturalize_text(text)
        text = self._fix_pronunciation(text)

        logger.info("Speaking (%s): '%s'", self._backend, text[:80])

        self._on_audio_ready = on_audio_ready
        self._on_audio_chunk = on_audio_chunk
        self._skip_local_playback = skip_local_playback

        try:
            if self._backend == "kokoro":
                await self._speak_kokoro(text)
            elif self._backend == "edge":
                await self._speak_edge(text)
            elif self._backend == "macos_say":
                await self._speak_macos(text)
            else:
                logger.error("No TTS backend configured.")
        except Exception as e:
            logger.error("TTS error (%s): %s", self._backend, e)
            if self._backend != "macos_say" and self._check_macos_say():
                logger.info("Falling back to macOS 'say' command.")
                await self._speak_macos(text)
        finally:
            self._on_audio_ready = None
            self._on_audio_chunk = None

    async def _speak_kokoro(self, text: str):
        """Generate and stream Kokoro TTS with chunked delivery."""
        if self._kokoro_pipeline is None:
            raise RuntimeError("Kokoro not initialized")

        import numpy as np
        import soundfile as sf
        import io

        loop = asyncio.get_event_loop()
        chunk_queue: asyncio.Queue = asyncio.Queue()

        def generate():
            chunk_count = 0
            for graphemes, phonemes, audio_chunk in self._kokoro_pipeline(
                text, voice=settings.TTS_VOICE, speed=settings.TTS_SPEED
            ):
                chunk_count += 1
                logger.debug(
                    "Kokoro chunk %d: '%s' (%d samples)",
                    chunk_count, graphemes[:50], len(audio_chunk)
                )
                loop.call_soon_threadsafe(chunk_queue.put_nowait, audio_chunk)
            logger.info(
                "Kokoro generated %d audio chunks for %d chars of text",
                chunk_count, len(text)
            )
            loop.call_soon_threadsafe(chunk_queue.put_nowait, None)

        gen_task = loop.run_in_executor(None, generate)

        all_chunks = []
        chunk_index = 0
        accumulated_samples = []
        accumulated_count = 0
        SAMPLES_PER_CHUNK_TARGET = int(24000 * 0.8)

        try:
            while True:
                audio_chunk = await chunk_queue.get()
                if audio_chunk is None:
                    break

                all_chunks.append(audio_chunk)
                accumulated_samples.append(audio_chunk)
                accumulated_count += len(audio_chunk)

                if self._on_audio_chunk and accumulated_count >= SAMPLES_PER_CHUNK_TARGET:
                    chunk_audio = np.concatenate(accumulated_samples)
                    chunk_duration = len(chunk_audio) / 24000
                    chunk_envelope = self._compute_amplitude_envelope(chunk_audio, 24000, fps=60)

                    wav_buf = io.BytesIO()
                    sf.write(wav_buf, chunk_audio, 24000, format="WAV")
                    chunk_b64, chunk_mime = await self._encode_for_browser(wav_buf.getvalue())

                    try:
                        await self._on_audio_chunk(
                            chunk_b64, chunk_index, False, chunk_envelope, chunk_duration
                        )
                    except Exception as e:
                        logger.warning("on_audio_chunk callback failed (chunk %d): %s", chunk_index, e)

                    chunk_index += 1
                    accumulated_samples = []
                    accumulated_count = 0
        except Exception as e:
            logger.error("Kokoro chunk streaming error: %s", e)

        await gen_task

        if self._on_audio_chunk and accumulated_samples:
            remaining_audio = np.concatenate(accumulated_samples)
            remaining_duration = len(remaining_audio) / 24000
            remaining_envelope = self._compute_amplitude_envelope(remaining_audio, 24000, fps=60)

            wav_buf = io.BytesIO()
            sf.write(wav_buf, remaining_audio, 24000, format="WAV")
            remaining_b64, _ = await self._encode_for_browser(wav_buf.getvalue())

            try:
                await self._on_audio_chunk(
                    remaining_b64, chunk_index, True, remaining_envelope, remaining_duration
                )
            except Exception as e:
                logger.warning("on_audio_chunk callback failed (final chunk %d): %s", chunk_index, e)
        elif self._on_audio_chunk and chunk_index > 0:
            try:
                await self._on_audio_chunk("", chunk_index, True, [], 0.0)
            except Exception as e:
                logger.warning("on_audio_chunk final signal failed: %s", e)

        if not all_chunks:
            logger.warning("Kokoro produced no audio for: '%s'", text[:80])
            return

        audio = np.concatenate(all_chunks)
        duration = len(audio) / 24000
        logger.info("Kokoro audio: %.1f seconds, %d samples (%d chunks streamed)",
                     duration, len(audio), chunk_index + 1 if chunk_index > 0 else 0)

        self._last_audio_duration = duration
        self._last_amplitude_envelope = self._compute_amplitude_envelope(audio, 24000, fps=60)

        temp_path = tempfile.mktemp(suffix=".wav")
        sf.write(temp_path, audio, 24000)

        wav_buffer = io.BytesIO()
        sf.write(wav_buffer, audio, 24000, format="WAV")
        audio_base64, audio_mime = await self._encode_for_browser(wav_buffer.getvalue())

        if self._on_audio_ready:
            try:
                await self._on_audio_ready(
                    self._last_amplitude_envelope, duration, audio_base64
                )
            except Exception as e:
                logger.warning("on_audio_ready callback failed: %s", e)

        if self._skip_local_playback:
            logger.info("Skipping local playback (browser-originated request)")
        else:
            await self._play_audio(temp_path)

        try:
            Path(temp_path).unlink()
        except Exception:
            pass

    async def _speak_edge(self, text: str):
        """Generate Edge TTS (Microsoft free voices) with browser streaming."""  # MP3 to WAV conversion
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            mp3_path = f.name

        communicate = edge_tts.Communicate(text, "en-US-GuyNeural")
        await communicate.save(mp3_path)

        wav_path = mp3_path + ".wav"
        audio_base64 = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", mp3_path,
                "-ar", "24000", "-ac", "1", "-f", "wav", wav_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()

            if proc.returncode == 0:
                wav_data = Path(wav_path).read_bytes()
                audio_base64 = base64.b64encode(wav_data).decode("ascii")

                import numpy as np
                import soundfile as sf
                audio_array, sr = sf.read(wav_path)
                duration = len(audio_array) / sr
                self._last_audio_duration = duration
                self._last_amplitude_envelope = self._compute_amplitude_envelope(
                    audio_array, sr, fps=60
                )

                if self._on_audio_ready:
                    try:
                        await self._on_audio_ready(
                            self._last_amplitude_envelope, duration, audio_base64
                        )
                    except Exception as e:
                        logger.warning("on_audio_ready callback failed (edge): %s", e)
        except Exception as e:
            logger.warning("Edge TTS browser audio encoding failed: %s", e)

        if self._skip_local_playback:
            logger.info("Skipping local playback (browser-originated request)")
        else:
            await self._play_audio(mp3_path)

        for p in [mp3_path, wav_path]:
            try:
                Path(p).unlink()
            except Exception:
                pass

    async def _speak_macos(self, text: str):
        """Generate macOS 'say' output with browser streaming and local playback."""
        temp_aiff = tempfile.mktemp(suffix=".aiff")
        wav_path = temp_aiff + ".wav"
        audio_base64 = None

        try:
            proc = await asyncio.create_subprocess_exec(
                "say", "-v", "Daniel", "-r", "190", "-o", temp_aiff, text,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()

            if proc.returncode == 0 and Path(temp_aiff).exists():
                conv_proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", temp_aiff,
                    "-ar", "24000", "-ac", "1", "-f", "wav", wav_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await conv_proc.wait()

                if conv_proc.returncode == 0 and Path(wav_path).exists():
                    wav_data = Path(wav_path).read_bytes()
                    audio_base64 = base64.b64encode(wav_data).decode("ascii")

                    try:
                        import numpy as np
                        import soundfile as sf
                        audio_array, sr = sf.read(wav_path)
                        duration = len(audio_array) / sr
                        self._last_audio_duration = duration
                        self._last_amplitude_envelope = self._compute_amplitude_envelope(
                            audio_array, sr, fps=60
                        )
                    except ImportError:
                        duration = 0.0
                        self._last_amplitude_envelope = []
                        self._last_audio_duration = 0.0

                    if self._on_audio_ready:
                        try:
                            await self._on_audio_ready(
                                self._last_amplitude_envelope, duration, audio_base64
                            )
                        except Exception as e:
                            logger.warning("on_audio_ready callback failed (macos): %s", e)
        except Exception as e:
            logger.warning("macOS say browser audio encoding failed: %s", e)

        if self._skip_local_playback:
            logger.info("Skipping local playback (browser-originated request)")
        elif Path(temp_aiff).exists():
            await self._play_audio(temp_aiff)
        else:
            process = await asyncio.create_subprocess_exec(
                "say", "-v", "Daniel", "-r", "190", text,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.wait()

        for p in [temp_aiff, wav_path]:
            try:
                Path(p).unlink()
            except Exception:
                pass

    async def _play_audio(self, filepath: str):
        """Play audio file using afplay or ffplay."""
        try:
            process = await asyncio.create_subprocess_exec(
                "afplay", filepath,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.wait()
        except FileNotFoundError:
            try:
                process = await asyncio.create_subprocess_exec(
                    "ffplay", "-nodisp", "-autoexit", filepath,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await process.wait()
            except FileNotFoundError:
                logger.error("No audio player found (afplay or ffplay).")

    def stop_speaking(self):
        """Stop any current speech output."""
        try:
            subprocess.run(
                ["killall", "say"], capture_output=True, timeout=2
            )
            subprocess.run(
                ["killall", "afplay"], capture_output=True, timeout=2
            )
        except Exception:
            pass

    @staticmethod
    async def _encode_for_browser(wav_bytes: bytes) -> tuple[str, str]:
        """Encode WAV for browser: Opus/WebM or fallback to WAV base64."""
        if settings.TTS_BROWSER_FORMAT == "opus":
            try:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wf:
                    wf.write(wav_bytes)
                    wav_path = wf.name
                opus_path = wav_path + ".webm"
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", wav_path,
                    "-c:a", "libopus", "-b:a", "48k",
                    "-vbr", "on", "-application", "voip",
                    "-f", "webm", opus_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()

                if proc.returncode == 0:
                    opus_bytes = Path(opus_path).read_bytes()
                    encoded = base64.b64encode(opus_bytes).decode("ascii")
                    wav_kb = len(wav_bytes) // 1024
                    opus_kb = len(opus_bytes) // 1024
                    ratio = wav_kb / max(opus_kb, 1)
                    logger.debug(
                        "Opus encoding: %d KB WAV -> %d KB Opus (%.1fx compression)",
                        wav_kb, opus_kb, ratio,
                    )
                    for p in [wav_path, opus_path]:
                        try:
                            Path(p).unlink()
                        except Exception:
                            pass
                    return encoded, "audio/webm;codecs=opus"

                logger.warning("Opus encoding failed (ffmpeg rc=%d), falling back to WAV", proc.returncode)
                for p in [wav_path, opus_path]:
                    try:
                        Path(p).unlink()
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("Opus encoding error: %s, falling back to WAV", e)

        return base64.b64encode(wav_bytes).decode("ascii"), "audio/wav"

    @staticmethod
    def _compute_amplitude_envelope(
        audio: "np.ndarray", sample_rate: int, fps: int = 60
    ) -> list[float]:
        """Compute RMS amplitude envelope for UI waveform visualization."""
        import numpy as np

        samples_per_frame = max(1, sample_rate // fps)
        envelope = []
        for i in range(0, len(audio), samples_per_frame):
            chunk = audio[i : i + samples_per_frame]
            rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
            envelope.append(rms)

        if envelope:
            peak = max(envelope)
            if peak > 0:
                envelope = [v / peak for v in envelope]

        return envelope

    def get_last_amplitude_envelope(self) -> tuple[list[float], float]:
        """Return (envelope, duration) for most recently generated audio."""
        return self._last_amplitude_envelope, self._last_audio_duration

    def get_backend_info(self) -> dict:
        """Return current TTS backend and availability status."""
        return {
            "backend": self._backend or "none",
            "kokoro_available": HAS_KOKORO,
            "edge_tts_available": HAS_EDGE_TTS,
            "macos_say_available": self._check_macos_say(),
        }
