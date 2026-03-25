"""JARVIS main entry point."""
import asyncio
import logging
import os
import signal
import sys

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

    logger.info("Initializing JARVIS components...")

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
    speaker_ok = speaker.initialize()

    listener.set_speaking(True)
    await speaker.speak("JARVIS online. All systems operational. How can I help you?")
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

    print("\nJARVIS is ready. Type your message (or 'quit' to exit).\n")

    if speaker_ok:
        await speaker.speak("JARVIS online. How can I help you?")

    while True:
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, input, "\nYou: "
            )
        except (KeyboardInterrupt, EOFError):
            break

        if user_input.lower() in ("quit", "exit", "bye", "goodbye"):
            print("\nJARVIS: Goodbye. Shutting down systems.")
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
        print(f"\nJARVIS: {response}")

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
    from jarvis.core.server import app, brain, broadcast_voice_interaction, broadcast_voice_state, broadcast_voice_chunk, set_voice_components
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

    async def run_voice_with_shared_brain():
        """Voice mode sharing server brain."""
        listener = VoiceListener()
        speaker = VoiceSpeaker()

        await asyncio.sleep(2)

        listener_ok = listener.initialize()
        speaker_ok = speaker.initialize()

        set_voice_components(speaker, listener)

        listener.set_speaking(True)
        await speaker.speak("JARVIS online. All systems operational. How can I help you?")
        listener.set_speaking(False)

        def on_wake():
            logger.info("* Wake word detected *")

        async def on_speech(text: str):
            logger.info("User said: %s", text)
            speaker.stop_speaking()
            listener.set_speaking(True)

            response = await brain.process(text)

            await broadcast_voice_interaction(text, response)

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

    await asyncio.gather(
        server.serve(),
        run_voice_with_shared_brain(),
    )


def _display_auth_info():
    """Display PIN authentication info."""

    from jarvis.core.server import get_startup_pin
    pin = get_startup_pin()
    if pin:
        print("  ==========================================")
        print(f"  Remote Access PIN:  {pin}")
        print("  ==========================================")
        print("  (Enter this PIN when connecting via phone)")
        print("  (Local connections bypass authentication)")
        print()
    else:
        print("  PIN authentication: loaded from previous session")
        print("  (Set JARVIS_REGEN_PIN=true to generate a new PIN)")
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
