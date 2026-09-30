"""JARVIS Screen Tools: screen capture and OCR using screencapture and Vision framework."""
import asyncio
import contextlib
import logging
import tempfile
import time
from pathlib import Path

from jarvis.config import settings

logger = logging.getLogger("jarvis.tools.screen")


async def capture_screen(output_path: str | None = None, region: str | None = None) -> str:
    """Capture a screenshot of the current screen."""
    if output_path is None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            output_path = tmp.name

    try:
        cmd = ["screencapture", "-x"]

        if region:
            cmd.extend(["-R", region])

        cmd.append(output_path)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        if Path(output_path).exists():
            logger.info("Screenshot saved: %s", output_path)
            return output_path
        else:
            return "Error: screenshot was not created."
    except Exception as e:
        return f"Error capturing screen: {e}"


async def capture_window(output_path: str | None = None) -> str:
    """Capture just the frontmost window."""
    if output_path is None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            output_path = tmp.name

    try:
        process = await asyncio.create_subprocess_exec(
            "screencapture", "-x", "-w", output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        if Path(output_path).exists():
            return output_path
        return "Error: window capture was not created."
    except Exception as e:
        return f"Error capturing window: {e}"


async def read_screen_text() -> str:
    """Capture the screen and extract all visible text using OCR."""
    screenshot_path = await capture_screen()
    if screenshot_path.startswith("Error"):
        return screenshot_path

    try:
        text = await _ocr_with_vision_framework(screenshot_path)
        if text:
            return text

        text = await _ocr_with_tesseract(screenshot_path)
        if text:
            return text

        return "OCR failed: no text extraction method available. Install tesseract: brew install tesseract"

    finally:
        with contextlib.suppress(Exception):
            Path(screenshot_path).unlink()


async def _ocr_with_vision_framework(image_path: str) -> str | None:
    """Use macOS Vision framework for OCR."""
    try:
        import Vision
        from Foundation import NSURL
        from Quartz import CIImage

        url = NSURL.fileURLWithPath_(image_path)
        ci_image = CIImage.imageWithContentsOfURL_(url)
        if ci_image is None:
            return None

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)

        handler = Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(
            ci_image, None
        )
        success = handler.performRequests_error_([request], None)

        if success:
            results = request.results()
            if results:
                texts = []
                for observation in results:
                    candidate = observation.topCandidates_(1)
                    if candidate:
                        texts.append(candidate[0].string())
                return "\n".join(texts)
        return None

    except ImportError:
        logger.debug("PyObjC Vision framework not available.")
        return None
    except Exception as e:
        logger.debug("Vision OCR error: %s", e)
        return None


async def _ocr_with_tesseract(image_path: str) -> str | None:
    """Fallback OCR using Tesseract."""
    try:
        process = await asyncio.create_subprocess_exec(
            "tesseract", image_path, "stdout",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()

        if process.returncode == 0:
            text = stdout.decode().strip()
            return text if text else None
        return None
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.debug("Tesseract OCR error: %s", e)
        return None


async def analyze_screen(question: str | None = None) -> str:
    """Capture the screen and analyze it with Claude's vision API.

    Takes a screenshot, sends it to the vision model with the optional question,
    and returns a natural language description of what's on screen.
    If no question is provided, gives a general summary.
    """
    import base64

    screenshot_path = await capture_screen()
    if screenshot_path.startswith("Error"):
        return screenshot_path

    try:
        # Read screenshot as base64
        image_data = Path(screenshot_path).read_bytes()
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        prompt = question or "Describe what you see on the screen. Focus on the active application, any important content, and what the user appears to be working on."

        from jarvis.core.hardening import cloud_circuit
        from jarvis.core.providers import build_provider, vision_spec

        provider = build_provider()
        if not provider.is_configured():
            return "Vision analysis unavailable: no cloud model API key is configured."
        if not cloud_circuit.allow_request():
            return "Vision analysis unavailable: the cloud model is temporarily unavailable."

        spec = vision_spec()
        start = time.time()
        try:
            text, usage = await provider.describe_image(
                image_b64=image_b64, media_type="image/png", prompt=prompt, spec=spec
            )
            cloud_circuit.record_success()
        except Exception:
            cloud_circuit.record_failure()
            raise
        _log_vision_cost(usage, time.time() - start)
        return text or "I captured the screen but couldn't analyze it."

    except Exception as e:
        logger.error("Screen analysis failed: %s", e)
        return f"Screen analysis error: {e}"
    finally:
        with contextlib.suppress(Exception):
            Path(screenshot_path).unlink()


def _log_vision_cost(usage, elapsed: float) -> None:
    try:
        from jarvis.core.cost_tracker import log_request

        log_request(
            model=usage.model, tier="vision",
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens, cache_creation_tokens=usage.cache_write_tokens,
            cost_usd=usage.cost(settings.MODEL_PRICING.get(usage.model, {})),
            elapsed_seconds=elapsed, user_input_preview="",
        )
    except Exception as exc:
        logger.debug("Vision cost log failed: %s", exc)


async def get_screen_size() -> str:
    """Get the current screen resolution."""
    try:
        process = await asyncio.create_subprocess_exec(
            "system_profiler", "SPDisplaysDataType",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        output = stdout.decode()

        # Extract resolution
        for line in output.split("\n"):
            if "Resolution" in line:
                return line.strip()

        return "Could not determine screen resolution."
    except Exception as e:
        return f"Error: {e}"
