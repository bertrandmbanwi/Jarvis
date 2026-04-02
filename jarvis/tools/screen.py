"""JARVIS Screen Tools: screen capture and OCR using screencapture and Vision framework."""
import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.tools.screen")


async def capture_screen(output_path: Optional[str] = None, region: Optional[str] = None) -> str:
    """Capture a screenshot of the current screen."""
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".png")

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


async def capture_window(output_path: Optional[str] = None) -> str:
    """Capture just the frontmost window."""
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".png")

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
        try:
            Path(screenshot_path).unlink()
        except Exception:
            pass


async def _ocr_with_vision_framework(image_path: str) -> Optional[str]:
    """Use macOS Vision framework for OCR."""
    try:
        import objc
        from Quartz import CIImage
        from Foundation import NSURL
        import Vision

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


async def _ocr_with_tesseract(image_path: str) -> Optional[str]:
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


async def analyze_screen(question: Optional[str] = None) -> str:
    """Capture the screen and analyze it with Claude's vision API.

    Takes a screenshot, sends it to Claude with the optional question,
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

        # Use the LLM module to analyze the image with Claude vision
        from jarvis.core.llm import JarvisLLM
        llm = JarvisLLM()
        if not llm._anthropic:
            llm._init_anthropic()

        if not llm._anthropic:
            return "Vision analysis unavailable: Claude API not configured."

        response = llm._anthropic.messages.create(
            model=settings.CLAUDE_FAST_MODEL,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        if response.content and len(response.content) > 0:
            return response.content[0].text
        return "I captured the screen but couldn't analyze it."

    except Exception as e:
        logger.error("Screen analysis failed: %s", e)
        return f"Screen analysis error: {e}"
    finally:
        try:
            Path(screenshot_path).unlink()
        except Exception:
            pass


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
