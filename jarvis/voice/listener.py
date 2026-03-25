"""JARVIS Voice Listener: microphone input, wake word detection, and speech-to-text."""
import asyncio
import logging
import numpy as np
import time
from typing import Callable, Optional

from jarvis.config import settings
from jarvis.core import profile

logger = logging.getLogger("jarvis.voice.listener")

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False
    logger.warning("PyAudio not installed. Voice input disabled.")

try:
    import openwakeword
    from openwakeword.model import Model as WakeWordModel
    HAS_WAKEWORD = True
except ImportError:
    HAS_WAKEWORD = False
    logger.warning("OpenWakeWord not installed. Wake word detection disabled.")

try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False
    logger.warning("faster-whisper not installed.")

if not HAS_WHISPER:
    try:
        import whisper
        HAS_WHISPER_ORIGINAL = True
    except ImportError:
        HAS_WHISPER_ORIGINAL = False
        logger.warning("No whisper library found. STT disabled.")
    else:
        HAS_WHISPER_ORIGINAL = True
else:
    HAS_WHISPER_ORIGINAL = False


class VoiceListener:
    """Listens for wake word, captures and transcribes speech."""

    def __init__(self):
        self._audio: Optional[object] = None
        self._stream: Optional[object] = None
        self._wake_model: Optional[object] = None
        self._whisper_model: Optional[object] = None
        self._is_listening = False
        self._is_speaking = False
        self._in_followup_window = False
        self._followup_start = 0.0
        self._last_wake_time = 0.0
        self._on_wake_callback: Optional[Callable] = None
        self._on_speech_callback: Optional[Callable] = None
        self.FOLLOWUP_WINDOW_SECONDS = 8.0
        self._followup_sustained_frames = 0
        self._followup_max_amplitude = 0.0

    def initialize(self) -> bool:
        """Set up audio, wake word model, and whisper."""
        success = True

        if HAS_PYAUDIO:
            try:
                self._audio = pyaudio.PyAudio()
                logger.info("PyAudio initialized. Input devices:")
                for i in range(self._audio.get_device_count()):
                    info = self._audio.get_device_info_by_index(i)
                    if info["maxInputChannels"] > 0:
                        logger.info(
                            "  [%d] %s (%.0f Hz)",
                            i, info["name"], info["defaultSampleRate"]
                        )
            except Exception as e:
                logger.error("PyAudio init failed: %s", e)
                success = False
        else:
            success = False

        if HAS_WAKEWORD:
            try:
                openwakeword.utils.download_models()
                self._wake_model = WakeWordModel(
                    wakeword_models=["hey_jarvis_v0.1"],
                    inference_framework="onnx",
                )
                logger.info("OpenWakeWord initialized (hey_jarvis model).")
            except Exception as e:
                logger.warning("Wake word init failed: %s. Will use keyboard activation.", e)
        else:
            logger.info("Wake word not available. Use keyboard to activate.")

        if HAS_WHISPER:
            try:
                self._whisper_model = WhisperModel(
                    settings.WHISPER_MODEL,
                    device="auto",
                    compute_type="int8",
                )
                logger.info("faster-whisper initialized (model: %s)", settings.WHISPER_MODEL)
            except Exception as e:
                logger.error("faster-whisper init failed: %s", e)
                success = False
        elif HAS_WHISPER_ORIGINAL:
            try:
                self._whisper_model = whisper.load_model(settings.WHISPER_MODEL)
                logger.info("Whisper (original) initialized (model: %s)", settings.WHISPER_MODEL)
            except Exception as e:
                logger.error("Whisper init failed: %s", e)
                success = False

        return success

    def on_wake(self, callback: Callable):
        """Register callback for when wake word is detected."""
        self._on_wake_callback = callback

    def on_speech(self, callback: Callable):
        """Register callback for when speech is transcribed."""
        self._on_speech_callback = callback

    def set_speaking(self, speaking: bool, open_followup: bool = True):
        """Set whether JARVIS is speaking; open follow-up window to listen without wake word."""
        self._is_speaking = speaking
        if not speaking:
            if open_followup:
                self._in_followup_window = True
                self._followup_start = time.time() + 0.5
                logger.info("Follow-up window open (%.0fs to respond without wake word).",
                            self.FOLLOWUP_WINDOW_SECONDS)
            else:
                self._in_followup_window = False
                logger.info("Resuming wake-word mode (no follow-up window for browser-originated response).")

    async def listen_loop(self):
        """Main listening loop: wait for wake word, record until silence, transcribe, callback."""
        if not HAS_PYAUDIO or self._audio is None:
            logger.error("Cannot start listening: PyAudio not available.")
            return

        self._is_listening = True
        logger.info("JARVIS is listening... Say 'Hey JARVIS' to activate.")

        try:
            self._stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=settings.AUDIO_CHANNELS,
                rate=settings.AUDIO_SAMPLE_RATE,
                input=True,
                frames_per_buffer=settings.AUDIO_CHUNK_SIZE,
            )
        except Exception as e:
            logger.error("Failed to open audio stream: %s", e)
            logger.info("Falling back to keyboard mode.")
            await self.listen_keyboard()
            return

        try:
            while self._is_listening:
                try:
                    audio_data = self._stream.read(
                        settings.AUDIO_CHUNK_SIZE, exception_on_overflow=False
                    )
                except Exception:
                    await asyncio.sleep(0.01)
                    continue

                audio_array = np.frombuffer(audio_data, dtype=np.int16)

                if self._is_speaking:
                    await asyncio.sleep(0.01)
                    continue

                if self._in_followup_window:
                    elapsed_followup = time.time() - self._followup_start
                    if elapsed_followup > self.FOLLOWUP_WINDOW_SECONDS:
                        self._in_followup_window = False
                        logger.info("Follow-up window closed. Say 'Hey JARVIS' to activate.")
                        continue

                    amplitude = np.abs(audio_array).mean()

                    if amplitude > settings.FOLLOWUP_SPEECH_SPIKE_THRESHOLD:
                        self._followup_sustained_frames += 1
                        self._followup_max_amplitude = max(self._followup_max_amplitude, amplitude)
                    else:
                        self._followup_sustained_frames = 0

                    if self._followup_sustained_frames >= settings.FOLLOWUP_SUSTAINED_FRAMES:
                        logger.info("Follow-up speech detected (sustained energy: %.0f). Recording...",
                                    self._followup_max_amplitude)
                        self._in_followup_window = False
                        self._followup_sustained_frames = 0
                        self._followup_max_amplitude = 0.0

                        speech_audio = await self._record_speech()
                        if speech_audio is not None:
                            text = self._transcribe(speech_audio)
                            if text and text.strip():
                                if self._is_meaningful_speech(text):
                                    logger.info("Transcribed (follow-up): '%s'", text)
                                    if self._on_speech_callback:
                                        await self._on_speech_callback(text)
                                else:
                                    self._in_followup_window = True
                                    self._followup_start = time.time()
                                    self._followup_sustained_frames = 0
                                    self._followup_max_amplitude = 0.0
                                    logger.info("Follow-up window re-opened after filtered speech.")

                    await asyncio.sleep(0.01)
                    continue

                wake_detected = self._check_wake_word(audio_array)

                if wake_detected:
                    now = time.time()
                    if now - self._last_wake_time < 3.0:
                        logger.debug("Wake word debounced (too soon after last trigger).")
                        continue
                    self._last_wake_time = now

                    logger.info("Wake word detected!")
                    if self._on_wake_callback:
                        self._on_wake_callback()

                    await asyncio.sleep(0.3)

                    speech_audio = await self._record_speech()

                    if speech_audio is not None:
                        text = self._transcribe(speech_audio)
                        if text and text.strip():
                            if self._is_meaningful_speech(text):
                                logger.info("Transcribed: '%s'", text)
                                if self._on_speech_callback:
                                    await self._on_speech_callback(text)
                            else:
                                logger.info("Filtered non-meaningful speech after wake word.")
                        else:
                            logger.info("No speech detected after wake word.")
                    else:
                        logger.info("Recording too short or empty.")

                await asyncio.sleep(0.01)

        except Exception as e:
            logger.error("Listen loop error: %s", e)
        finally:
            self._cleanup_stream()

    def _get_transcription_hints(self) -> tuple[Optional[str], Optional[list[str]]]:
        """Build initial_prompt and hotwords from user profile for better transcription."""
        if not settings.WHISPER_USE_LOCATION_HINTS:
            return None, None

        try:
            user_profile = profile.get_profile()
            city = user_profile.get("location_city", "").strip()
            state = user_profile.get("location_state", "").strip()
            nearby = user_profile.get("nearby_cities", [])
            name = user_profile.get("name", "").strip()

            prompt_parts = []
            if city and state:
                prompt_parts.append(f"The user lives in {city}, {state}.")
            if nearby and isinstance(nearby, list):
                nearby_str = ", ".join(nearby)
                prompt_parts.append(f"Nearby cities include {nearby_str}.")

            initial_prompt = " ".join(prompt_parts) if prompt_parts else None

            hotwords = []
            if city:
                hotwords.append(city)
            if state:
                hotwords.append(state)
            if nearby and isinstance(nearby, list):
                hotwords.extend(nearby)
            if name:
                hotwords.append(name)

            hotwords.extend(["Dallas", "Texas"])

            seen = set()
            unique_hotwords = []
            for word in hotwords:
                lower_word = word.lower()
                if lower_word not in seen:
                    seen.add(lower_word)
                    unique_hotwords.append(word)

            return initial_prompt, unique_hotwords if unique_hotwords else None

        except Exception as e:
            logger.warning("Failed to build transcription hints: %s", e)
            return None, None

    def _check_wake_word(self, audio_chunk: np.ndarray) -> bool:
        """Check if the audio chunk contains the wake word."""
        if self._wake_model is None:
            return False

        try:
            prediction = self._wake_model.predict(audio_chunk)
            for model_name, score in prediction.items():
                if score > settings.WAKE_WORD_THRESHOLD:
                    logger.debug("Wake word '%s' score: %.3f", model_name, score)
                    self._wake_model.reset()
                    return True
            return False
        except Exception as e:
            logger.debug("Wake word check error: %s", e)
            return False

    async def _record_speech(self) -> Optional[np.ndarray]:
        """Record speech until silence detected; return numpy array or None if too short."""
        logger.info("Listening... (speak now, threshold=%d)", settings.SILENCE_THRESHOLD)
        frames = []
        silence_start = None
        has_heard_speech = False
        recording_start = time.time()
        max_amplitude_seen = 0
        log_interval = 0  # For periodic amplitude logging

        while True:
            elapsed = time.time() - recording_start
            if elapsed > settings.MAX_RECORDING_DURATION:
                logger.info("Max recording duration reached (%.0fs).", elapsed)
                break

            try:
                audio_data = self._stream.read(
                    settings.AUDIO_CHUNK_SIZE, exception_on_overflow=False
                )
            except Exception:
                break

            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            frames.append(audio_array)

            amplitude = np.abs(audio_array).mean()
            max_amplitude_seen = max(max_amplitude_seen, amplitude)

            log_interval += 1
            if log_interval % 6 == 0:
                logger.info(
                    "  [mic] amplitude: %.0f (threshold: %d, max seen: %.0f, speech: %s)",
                    amplitude, settings.SILENCE_THRESHOLD, max_amplitude_seen,
                    "yes" if has_heard_speech else "no"
                )

            if amplitude > settings.SILENCE_THRESHOLD:
                has_heard_speech = True
                silence_start = None
            else:
                if has_heard_speech:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > settings.SILENCE_DURATION:
                        logger.info("End of speech detected (max amplitude was %.0f).", max_amplitude_seen)
                        break
                else:
                    if elapsed > 8.0:
                        logger.info(
                            "No speech detected within 8 seconds. "
                            "Max amplitude was %.0f (threshold is %d). "
                            "If this keeps happening, lower SILENCE_THRESHOLD in settings.",
                            max_amplitude_seen, settings.SILENCE_THRESHOLD
                        )
                        return None

            await asyncio.sleep(0.005)

        if not frames:
            return None

        combined = np.concatenate(frames)
        duration = len(combined) / settings.AUDIO_SAMPLE_RATE
        logger.info("Recorded %.1f seconds of audio (amplitude peaks detected: %s).",
                     duration, "yes" if has_heard_speech else "no")

        if duration < 0.5 or not has_heard_speech:
            return None

        return combined

    def _transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio to text using Whisper with optional location hints."""
        if self._whisper_model is None:
            logger.error("No STT model available.")
            return ""

        try:
            audio_float = audio.astype(np.float32) / 32768.0

            if HAS_WHISPER:
                initial_prompt, hotwords = self._get_transcription_hints()

                transcribe_kwargs = {
                    "language": settings.WHISPER_LANGUAGE,
                    "beam_size": settings.WHISPER_BEAM_SIZE,
                    "vad_filter": False,
                }

                if initial_prompt:
                    transcribe_kwargs["initial_prompt"] = initial_prompt
                    logger.debug("Using initial_prompt: %s", initial_prompt)

                if hotwords:
                    transcribe_kwargs["hotwords"] = hotwords
                    logger.debug("Using hotwords: %s", ", ".join(hotwords))

                segments, info = self._whisper_model.transcribe(audio_float, **transcribe_kwargs)
                text = " ".join(segment.text for segment in segments)

            elif HAS_WHISPER_ORIGINAL:
                result = self._whisper_model.transcribe(
                    audio_float,
                    language=settings.WHISPER_LANGUAGE,
                    fp16=False,
                )
                text = result.get("text", "")
            else:
                return ""

            return text.strip()

        except Exception as e:
            logger.error("Transcription error: %s", e)
            return ""

    def _is_meaningful_speech(self, text: str) -> bool:
        """Filter out known Whisper hallucinations on silence/noise. Errs on side of inclusion."""
        if not text or not text.strip():
            return False

        cleaned = text.strip().lower().rstrip(".!?, ")

        hallucination_exact = {
            "thank you for watching",
            "thanks for watching",
            "please subscribe",
            "like and subscribe",
            "subscribe",
            "you",
            "",
        }
        if cleaned in hallucination_exact:
            logger.info("Filtered Whisper hallucination: '%s'", text)
            return False

        import re
        phrases = [p.strip().rstrip(".!?,") for p in re.split(r'[.!?,]+', cleaned) if p.strip()]
        if len(phrases) >= 4:
            filler_words = {
                "okay", "ok", "all right", "alright", "right", "um", "uh",
                "hmm", "hm", "yeah", "yep", "so", "oh", "ah", "mhm",
            }
            filler_count = sum(1 for p in phrases if p in filler_words)
            if filler_count == len(phrases):
                logger.info("Filtered pure filler (%d phrases): '%s'", len(phrases), text)
                return False

        return True

    async def listen_keyboard(self):
        """Keyboard-activated listening (fallback): press Enter to record."""
        logger.info("Keyboard mode: Press Enter to speak, Ctrl+C to quit.")
        self._is_listening = True

        while self._is_listening:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, input, "\n[Press Enter to speak] "
                )

                if self._on_wake_callback:
                    self._on_wake_callback()

                if not HAS_PYAUDIO or self._audio is None:
                    logger.error("PyAudio not available.")
                    continue

                self._stream = self._audio.open(
                    format=pyaudio.paInt16,
                    channels=settings.AUDIO_CHANNELS,
                    rate=settings.AUDIO_SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=settings.AUDIO_CHUNK_SIZE,
                )

                speech_audio = await self._record_speech()
                self._cleanup_stream()

                if speech_audio is not None:
                    text = self._transcribe(speech_audio)
                    if text and text.strip():
                        logger.info("You said: '%s'", text)
                        if self._on_speech_callback:
                            await self._on_speech_callback(text)

            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                logger.error("Keyboard listen error: %s", e)

    def _cleanup_stream(self):
        """Close and reset audio stream."""  # Simple cleanup
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def stop(self):
        """Stop the listening loop."""
        self._is_listening = False
        self._cleanup_stream()

    def cleanup(self):
        """Terminate listener and close audio resources."""
        self.stop()
        if self._audio is not None:
            try:
                self._audio.terminate()
            except Exception:
                pass
