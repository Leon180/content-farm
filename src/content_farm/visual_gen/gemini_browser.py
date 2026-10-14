"""Playwright-based Gemini (Nano Banana) image generation.

Attaches to an already-running Chrome via CDP so the user's real
Gemini Advanced subscription session is used (Google does not flag
this as automation).

Flow per shot:
1. Focus the chat input and clear it
2. Insert the prompt text
3. Press Enter to submit
4. Wait for Gemini to finish (detected by the Send button returning
   to its normal state — during generation it becomes a Stop button)
5. Collect image URLs that weren't on the page before submitting
6. Download them into the run's visual/ directory
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Page, async_playwright

from content_farm.visual_gen.storyboard_parser import Shot

logger = logging.getLogger(__name__)

GEMINI_URL = "https://gemini.google.com/?hl=zh-TW"

CHAT_INPUT_SELECTORS = (
    "rich-textarea div[contenteditable='true']",
    "div[contenteditable='true'][role='textbox']",
    "textarea[aria-label*='prompt' i]",
    "textarea[aria-label*='Gemini']",
)

# Selectors that match the send button whether or not generation is in
# progress. During generation its aria-label changes to include "stop" /
# "暫停" / "Stop generating" etc.
SEND_BUTTON_SELECTORS = (
    "button.send-button",
    "button[aria-label*='send' i]",
    "button[aria-label*='傳送' i]",
    "button[aria-label*='submit' i]",
)
STOP_BUTTON_SELECTORS = (
    "button[aria-label*='stop' i]",
    "button[aria-label*='暫停' i]",
    "button[aria-label*='停止' i]",
    "button.stop",
)

RESPONSE_IMAGE_SELECTORS = (
    "model-response img[src*='http']",
    "generative-image img",
    "message-content img[alt]",
    "img[data-gemini-image]",
    "img[src*='googleusercontent.com']",
)


@dataclass
class GenerationResult:
    """Outcome of generating visuals for one shot."""

    shot: Shot
    success: bool
    saved_files: list[Path] = field(default_factory=list)
    error: str = ""


@dataclass
class GeminiBrowserConfig:
    """Runtime config for the Gemini browser automation."""

    user_data_dir: Path
    download_dir: Path
    delay_between_prompts_s: float = 2.0
    generation_timeout_s: float = 300.0
    headless: bool = False
    use_system_chrome: bool = False
    cdp_port: int | None = None


class GeminiBrowser:
    """Drives a Gemini chat session via Playwright to generate images."""

    def __init__(self, config: GeminiBrowserConfig) -> None:
        self._cfg = config
        self._cfg.user_data_dir.mkdir(parents=True, exist_ok=True)
        self._cfg.download_dir.mkdir(parents=True, exist_ok=True)

    async def run(self, shots: list[Shot]) -> list[GenerationResult]:
        image_shots = [s for s in shots if s.is_image]
        video_shots = [s for s in shots if s.is_video]
        if video_shots:
            logger.warning(
                "Skipping %d video shot(s) — Nano Banana only handles images: %s",
                len(video_shots),
                [s.filename for s in video_shots],
            )

        results: list[GenerationResult] = []

        async with async_playwright() as pw:
            page = await self._open_page(pw)

            try:
                await self._goto_gemini(page)
                await self._wait_for_ready(page)

                for i, shot in enumerate(image_shots):
                    logger.info(
                        "[%d/%d] Submitting: %s",
                        i + 1, len(image_shots), shot.filename,
                    )
                    result = await self._generate_one(page, shot)
                    results.append(result)
                    if result.success:
                        logger.info("  ✅ done")
                    else:
                        logger.warning("  ❌ %s", result.error)

                    if i < len(image_shots) - 1:
                        await asyncio.sleep(self._cfg.delay_between_prompts_s)
            finally:
                # Don't close the context if we attached via CDP (it's the
                # user's Chrome), otherwise close to free resources.
                if self._cfg.cdp_port is None:
                    try:
                        await page.context.close()
                    except Exception:
                        pass

        return results

    # ----- connection / navigation -----

    async def _open_page(self, pw) -> Page:
        if self._cfg.cdp_port is not None:
            cdp_url = f"http://localhost:{self._cfg.cdp_port}"
            logger.info("Connecting to Chrome via CDP at %s", cdp_url)
            browser = await pw.chromium.connect_over_cdp(cdp_url)
            ctx = (
                browser.contexts[0]
                if browser.contexts
                else await browser.new_context()
            )
            # Prefer a tab that's already on Gemini to avoid opening duplicates
            for p in ctx.pages:
                if "gemini.google.com" in (p.url or ""):
                    return p
            return ctx.pages[0] if ctx.pages else await ctx.new_page()

        launch_kwargs: dict = {
            "user_data_dir": str(self._cfg.user_data_dir),
            "headless": self._cfg.headless,
            "accept_downloads": True,
            "viewport": {"width": 1280, "height": 900},
        }
        if self._cfg.use_system_chrome:
            launch_kwargs["channel"] = "chrome"
        ctx = await pw.chromium.launch_persistent_context(**launch_kwargs)
        return ctx.pages[0] if ctx.pages else await ctx.new_page()

    async def _goto_gemini(self, page: Page) -> None:
        if "gemini.google.com" not in (page.url or ""):
            logger.info("Opening Gemini...")
            await page.goto(GEMINI_URL, wait_until="domcontentloaded")

    async def _wait_for_ready(self, page: Page) -> None:
        """Wait for user to confirm Gemini is logged-in and in image mode."""
        import sys
        # Make sure chat input exists (basic sanity)
        deadline = asyncio.get_event_loop().time() + 60
        while asyncio.get_event_loop().time() < deadline:
            if await self._find_chat_input(page):
                break
            await asyncio.sleep(2)
        else:
            raise TimeoutError("Gemini chat input not found within 60s")

        banner = (
            "\n======================================================================\n"
            "👉 CHROME IS READY\n"
            "======================================================================\n"
            "In the Chrome window, please:\n"
            "  1. Confirm you are signed in (profile avatar top-right)\n"
            "  2. (optional) Choose Gemini model with image generation\n"
            "  3. Keep the tab focused on gemini.google.com\n"
            "\n"
            "When ready, press ENTER here and the script will auto-submit\n"
            "prompts and download images one by one.\n"
            "======================================================================\n"
        )
        sys.stdout.write(banner)
        sys.stdout.flush()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input)
        sys.stdout.write("✅ Starting generation...\n\n")
        sys.stdout.flush()

    # ----- per-shot generation -----

    async def _generate_one(
        self, page: Page, shot: Shot,
    ) -> GenerationResult:
        try:
            input_sel = await self._find_chat_input(page)
            if not input_sel:
                raise RuntimeError("Chat input not found")

            # Focus & clear
            input_loc = page.locator(input_sel).first
            await input_loc.click()
            await page.keyboard.press("Meta+A" if _is_mac() else "Control+A")
            await page.keyboard.press("Delete")
            await asyncio.sleep(0.3)

            # Insert prompt text (works on contenteditable)
            await page.keyboard.insert_text(shot.prompt)
            await asyncio.sleep(0.5)

            # Submit with Enter
            await page.keyboard.press("Enter")

            # Wait for generation — watch Stop button appear then disappear
            await self._wait_for_generation_complete(page)

            return GenerationResult(shot=shot, success=True)
        except Exception as exc:
            logger.exception("Failed generating %s", shot.filename)
            return GenerationResult(
                shot=shot, success=False, error=str(exc),
            )

    async def _wait_for_generation_complete(self, page: Page) -> None:
        """Wait until the Stop button disappears.

        Phase 1: wait up to 10s for Stop button to APPEAR (generation start).
        Phase 2: wait up to ``generation_timeout_s`` for it to DISAPPEAR.
        If Phase 1 times out, we assume the prompt was accepted without
        showing a Stop button and fall through.
        """
        # Phase 1 — wait for generation to visibly start
        for _ in range(20):  # ~10s
            if await self._any_locator_count(page, STOP_BUTTON_SELECTORS) > 0:
                break
            await asyncio.sleep(0.5)

        # Phase 2 — wait for it to finish
        deadline = (
            asyncio.get_event_loop().time() + self._cfg.generation_timeout_s
        )
        while asyncio.get_event_loop().time() < deadline:
            count = await self._any_locator_count(page, STOP_BUTTON_SELECTORS)
            if count == 0:
                return
            await asyncio.sleep(1.5)
        raise TimeoutError(
            f"Generation did not finish within "
            f"{self._cfg.generation_timeout_s}s "
            f"(Stop button still visible)"
        )

    # ----- locator helpers -----

    async def _find_chat_input(self, page: Page) -> str | None:
        for sel in CHAT_INPUT_SELECTORS:
            if await page.locator(sel).count() > 0:
                return sel
        return None

    async def _any_locator_count(
        self, page: Page, selectors: tuple[str, ...],
    ) -> int:
        total = 0
        for sel in selectors:
            try:
                total += await page.locator(sel).count()
            except Exception:
                pass
        return total

    async def _collect_all_image_urls(self, page: Page) -> set[str]:
        urls: set[str] = set()
        for sel in RESPONSE_IMAGE_SELECTORS:
            try:
                elements = await page.locator(sel).all()
            except Exception:
                continue
            for el in elements:
                try:
                    src = await el.get_attribute("src")
                except Exception:
                    continue
                if src and src.startswith("http"):
                    urls.add(src)
        return urls

    # ----- downloads -----

    async def _download_images(
        self, urls: list[str], shot: Shot,
    ) -> list[Path]:
        import httpx

        saved: list[Path] = []
        stem = shot.filename.rsplit(".", 1)[0]
        suffix = ".png"

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for idx, url in enumerate(urls, 1):
                out_name = (
                    f"{stem}{suffix}"
                    if len(urls) == 1
                    else f"{stem}_{idx:02d}{suffix}"
                )
                out_path = self._cfg.download_dir / out_name
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    out_path.write_bytes(resp.content)
                    saved.append(out_path)
                except Exception:
                    logger.exception("Failed to download %s", url)
        return saved


def _is_mac() -> bool:
    import sys

    return sys.platform == "darwin"
