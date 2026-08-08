"""JARVIS main entry point."""
import asyncio
import logging
import os
import sys
from collections.abc import Coroutine
from typing import Any

from jarvis.config import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.LOG_FILE, mode="a"),
    ],
)
logger = logging.getLogger("jarvis")

# Strong references to fire-and-forget voice tasks so asyncio does not
# garbage-collect (and silently cancel) them while they are still running.
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Schedule a background task and retain a reference until it completes."""
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


BANNER = r"""
       ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
       ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
       ██║███████║██████╔╝██║   ██║██║███████╗
  ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
  ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
   ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
  Just A Rather Very Intelligent System  v0.3.0
"""


async def run_voice_mode():
    """Run JARVIS in voice mode."""
    from jarvis.core.brain import JarvisBrain
    from jarvis.voice.listener import VoiceListener
    from jarvis.voice.speaker import VoiceSpeaker

    brain = JarvisBrain()
    listener = VoiceListener()
    speaker = VoiceSpeaker()

    logger.info("Initializing MayAss components...")

    brain_ok = await brain.initialize()
    if not brain_ok:
        logger.error(
            "Brain failed to initialize. Make sure Ollama is running:\n"
            "  1. Open a terminal\n"
            "  2. Run: ollama serve\n"
            "  3. Run: ollama pull llama3.1:8b\n"
            "  4. Try again"
        )
        return

    listener_ok = listener.initialize()
    speaker.initialize()

    listener.set_speaking(True)
    await speaker.speak("Maymint online. All systems operational. How can I help you?")
    listener.set_speaking(False)

    def on_wake():
        logger.info("* Wake word detected *")

    async def on_speech(text: str):
        logger.info("User said: %s", text)

        speaker.stop_speaking()
        listener.set_speaking(True)

        response = await brain.process(text)

        await speaker.speak(response)

        if brain._shutdown_requested:
            logger.info("Shutdown requested. Stopping listener.")
            listener.stop()
            return

        listener.set_speaking(False)

    listener.on_wake(on_wake)
    listener.on_speech(on_speech)

    if listener_ok and listener._wake_model is not None:
        logger.info("Starting voice mode with wake word detection...")
        await listener.listen_loop()
    else:
        logger.info("Starting keyboard-activated voice mode...")
        logger.info("(Wake word not available; press Enter to speak)")
        await listener.listen_keyboard()

    listener.cleanup()
    await brain.shutdown()


async def run_text_mode():
    """Run JARVIS in text mode."""
    from jarvis.core.brain import JarvisBrain
    from jarvis.voice.speaker import VoiceSpeaker

    brain = JarvisBrain()
    speaker = VoiceSpeaker()

    brain_ok = await brain.initialize()
    if not brain_ok:
        logger.error(
            "Brain failed to initialize. Make sure Ollama is running:\n"
            "  1. Open a terminal\n"
            "  2. Run: ollama serve\n"
            "  3. Run: ollama pull llama3.1:8b\n"
            "  4. Try again"
        )
        return

    speaker_ok = speaker.initialize()

    print("\nMaymint is ready. Type your message (or 'quit' to exit).\n")

    if speaker_ok:
        await speaker.speak("Maymint online. How can I help you?")

    while True:
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, input, "\nYou: "
            )
        except (KeyboardInterrupt, EOFError):
            break

        if user_input.lower() in ("quit", "exit", "bye", "goodbye"):
            print("\nMaymint: Goodbye. Shutting down systems.")
            if speaker_ok:
                await speaker.speak("Goodbye. Shutting down systems.")
            break

        if not user_input.strip():
            continue

        if user_input.strip() == "/status":
            print(f"\n[Status] {brain.get_conversation_summary()}")
            print(f"[Memory] {brain.memory.get_stats()}")
            continue
        if user_input.strip() == "/clear":
            brain.clear_conversation()
            print("\n[Conversation cleared]")
            continue

        response = await brain.process(user_input)
        print(f"\nMaymint: {response}")

        if speaker_ok:
            await speaker.speak(response)

        if brain._shutdown_requested:
            break

    await brain.shutdown()


async def run_server_mode():
    """Run JARVIS as API server."""
    import uvicorn

    from jarvis.core.server import app

    ssl_certfile = os.environ.get("JARVIS_TLS_CERT")
    ssl_keyfile = os.environ.get("JARVIS_TLS_KEY")
    uvicorn_kwargs = dict(
        app=app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="info",
    )
    if ssl_certfile and ssl_keyfile:
        uvicorn_kwargs["ssl_certfile"] = ssl_certfile
        uvicorn_kwargs["ssl_keyfile"] = ssl_keyfile

    config = uvicorn.Config(**uvicorn_kwargs)
    server = uvicorn.Server(config)
    await server.serve()


async def run_full():
    """Run API server and voice listener concurrently."""
    import uvicorn

    from jarvis.core.server import (
        app,
        brain,
        broadcast_overlay_state,
        broadcast_voice_chunk,
        broadcast_voice_interaction,
        broadcast_voice_state,
        set_voice_components,
    )
    from jarvis.voice.listener import VoiceListener
    from jarvis.voice.speaker import VoiceSpeaker

    ssl_certfile = os.environ.get("JARVIS_TLS_CERT")
    ssl_keyfile = os.environ.get("JARVIS_TLS_KEY")
    uvicorn_kwargs = dict(
        app=app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="warning",
    )
    if ssl_certfile and ssl_keyfile:
        uvicorn_kwargs["ssl_certfile"] = ssl_certfile
        uvicorn_kwargs["ssl_keyfile"] = ssl_keyfile
        logger.info("API server: HTTPS enabled (cert: %s)", ssl_certfile)

    config = uvicorn.Config(**uvicorn_kwargs)
    server = uvicorn.Server(config)
    listener_ref = None
    speaker_ref = None

    async def run_voice_with_shared_brain():
        """Voice mode sharing server brain."""
        nonlocal listener_ref, speaker_ref
        listener = VoiceListener()
        speaker = VoiceSpeaker()
        listener_ref = listener
        speaker_ref = speaker

        try:
            await asyncio.sleep(2)

            listener_ok = listener.initialize()
            speaker.initialize()

            set_voice_components(speaker, listener)

            listener.set_speaking(True)
            await speaker.speak("Maymint online. All systems operational. How can I help you?")
            listener.set_speaking(False)
        except asyncio.CancelledError:
            listener.cleanup()
            speaker.stop_speaking()
            raise

        def on_wake():
            logger.info("* Wake word detected *")
            _spawn_background(broadcast_overlay_state("listening"))

        async def _speak_response(response: str):
            """Speak a response and broadcast to all UI clients."""
            await broadcast_overlay_state("speaking", text=response)

            async def on_audio_ready(envelope, duration, audio_b64=None):
                await broadcast_voice_state(
                    True,
                    amplitude_envelope=envelope,
                    audio_duration=duration,
                    audio_base64=audio_b64,
                )

            async def on_audio_chunk(chunk_b64, idx, is_last, env, dur):
                await broadcast_voice_chunk(
                    chunk_b64, idx, is_last, env, dur,
                )

            await speaker.speak(
                response,
                on_audio_ready=on_audio_ready,
                on_audio_chunk=on_audio_chunk,
            )
            await broadcast_voice_state(False)
            await broadcast_overlay_state("idle")
            listener.set_speaking(False)

        def _needs_async_execution(text: str) -> bool:
            """Determine if a request should run async (immediate ack, background processing).

            Returns True for complex tasks that involve planning or multi-step execution.
            Returns False for chat, greetings, quick lookups (these respond fast enough inline).
            """
            from jarvis.core.brain import _is_chat_only, _select_tier
            tier = _select_tier(text)
            # Fast-tier chat is already quick; no need for async
            if tier == "fast" and _is_chat_only(text):
                return False
            # Short conversational messages are fast enough inline
            if len(text.split()) < 8 and tier != "deep":
                return False
            # Look for signals of complex work
            complex_signals = [
                "build", "create", "scaffold", "deploy", "write code",
                "research", "analyze", "investigate", "compare",
                "set up", "configure", "install", "refactor",
                "find and", "search and", "go to", "open and",
            ]
            text_lower = text.lower()
            for signal in complex_signals:
                if signal in text_lower:
                    return True
            # Deep tier always gets async treatment
            return tier == "deep"

        async def _run_async_task(text: str):
            """Run brain.process in background; speak result when done."""
            try:
                response = await brain.process(text)
                await broadcast_voice_interaction(text, response)
                listener.set_speaking(True)
                await _speak_response(response)

                if brain._shutdown_requested:
                    logger.info("Shutdown requested. Stopping listener.")
                    listener.stop()
            except Exception as e:
                logger.error("Async task failed: %s", e)
                listener.set_speaking(True)
                await _speak_response(
                    f"I ran into an issue processing that request, sir. {str(e)[:100]}"
                )

        async def on_speech(text: str):
            logger.info("User said: %s", text)
            speaker.stop_speaking()
            listener.set_speaking(True)

            if _needs_async_execution(text):
                # Complex task: acknowledge immediately, process in background
                logger.info("Async execution: acknowledging and processing in background.")
                await broadcast_overlay_state("speaking", user_text=text)
                ack_phrases = [
                    "On it, sir.",
                    "Working on that now.",
                    "Let me handle that.",
                    "I'll get right on it, sir.",
                ]
                import secrets
                ack = secrets.choice(ack_phrases)
                await speaker.speak(ack)
                listener.set_speaking(False)
                await broadcast_overlay_state("thinking", user_text=text)
                # Fire and forget: brain processes in background
                _spawn_background(_run_async_task(text))
            else:
                # Quick request: process inline (fast enough for real-time voice)
                await broadcast_overlay_state("thinking", user_text=text)
                response = await brain.process(text)
                await broadcast_voice_interaction(text, response)
                await _speak_response(response)

                if brain._shutdown_requested:
                    logger.info("Shutdown requested. Stopping listener.")
                    listener.stop()
                    return

        listener.on_wake(on_wake)
        listener.on_speech(on_speech)

        from jarvis.core import pending_actions
        from jarvis.voice.confirm import run_voice_confirmation

        async def _voice_confirmation_notifier(payload):
            conf = payload.get("confirmation")
            if conf:
                _spawn_background(
                    run_voice_confirmation(speaker, listener, conf["id"], conf["summary"])
                )

        pending_actions.add_notifier(_voice_confirmation_notifier)

        try:
            if listener_ok:
                if listener._wake_model is not None:
                    logger.info("Starting voice mode with wake word and desktop hotkey activation...")
                else:
                    logger.info("Starting voice mode with desktop hotkey activation...")
                    logger.info("(Wake word not available; press Control+Option+J to speak)")
                await listener.listen_loop()
            else:
                logger.info("Starting keyboard-activated voice mode...")
                logger.info("(Wake word not available; press Enter to speak)")
                await listener.listen_keyboard()
        except asyncio.CancelledError:
            listener.stop()
            raise
        finally:
            pending_actions.remove_notifier(_voice_confirmation_notifier)
            listener.cleanup()
            speaker.stop_speaking()

    server_task = asyncio.create_task(server.serve(), name="jarvis-api-server")
    voice_task = asyncio.create_task(run_voice_with_shared_brain(), name="jarvis-voice-listener")
    tasks = {server_task, voice_task}

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None and not isinstance(exc, asyncio.CancelledError):
                raise exc

        server.should_exit = True
        if listener_ref:
            listener_ref.stop()
        if speaker_ref:
            speaker_ref.stop_speaking()

        for task in pending:
            task.cancel()

        await asyncio.gather(*pending, return_exceptions=True)
    except KeyboardInterrupt:
        server.should_exit = True
        if listener_ref:
            listener_ref.stop()
        if speaker_ref:
            speaker_ref.stop_speaking()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _display_auth_info():
    """Display browser/mobile authentication info."""

    from jarvis.core import auth
    from jarvis.core.server import get_startup_pin

    if not auth.pin_auth_enabled():
        print("  PIN authentication: disabled")
        print("  (Set JARVIS_PIN_AUTH_ENABLED=true to require a PIN for remote access)")
        print()
        return

    pin = get_startup_pin()
    if pin:
        print("  ==========================================")
        print(f"  Remote Access PIN:  {pin}")
        print("  ==========================================")
        print("  (Enter this PIN when connecting via phone)")
        print("  (Local connections bypass authentication)")
        print()
    else:
        print("  PIN authentication: using saved PIN")
        print("  (Unset JARVIS_REGEN_PIN or set it to true to generate a new PIN)")
        print()


def main():
    """CLI entry point."""

    print(BANNER)

    mode = "text"  # Default mode
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()

    if mode == "voice":
        print("Starting in VOICE mode...\n")
        asyncio.run(run_voice_mode())
    elif mode == "server":
        print(f"Starting API SERVER on http://localhost:{settings.API_PORT}\n")
        _display_auth_info()
        asyncio.run(run_server_mode())
    elif mode == "full":
        print(f"Starting FULL mode (voice + server on port {settings.API_PORT})...\n")
        _display_auth_info()
        asyncio.run(run_full())
    else:
        print("Starting in TEXT mode (type to chat)...\n")
        print("  Other modes:")
        print("    python -m jarvis.main voice    (voice interaction)")
        print("    python -m jarvis.main server   (API server only)")
        print("    python -m jarvis.main full     (voice + API server)")
        print()
        asyncio.run(run_text_mode())


if __name__ == "__main__":
    main()
