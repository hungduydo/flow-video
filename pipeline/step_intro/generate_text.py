"""Generate Vietnamese intro text using LLM."""

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Vietnamese video intro writer. Generate a short, punchy hook (30-100 Vietnamese characters) that grabs attention based on the video title and transcript.

Write ONLY the intro text in Vietnamese, no quotes, no explanation, no markdown.
Keep it SHORT and exciting.
Make it relevant to the content."""


def generate_intro(
    title: str,
    captions_sample: str,
    llm_provider: str = "claude"
) -> str:
    """
    Generate 30-100 character Vietnamese intro text.

    Args:
        title: Video title
        captions_sample: First 5-10 captions concatenated (~300 chars)
        llm_provider: "claude" or "gemini"

    Returns:
        Vietnamese intro text (30-100 chars)
    """
    caption_excerpt = captions_sample[:300] if captions_sample else ""

    user_prompt = f"""Video Title: {title}

Transcript excerpt: {caption_excerpt}

Generate the intro text now."""

    try:
        if llm_provider == "claude":
            from anthropic import Anthropic

            client = Anthropic()
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            intro_text = response.content[0].text.strip()
        elif llm_provider == "gemini":
            import google.generativeai as genai

            genai.configure()
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(f"{SYSTEM_PROMPT}\n\n{user_prompt}")
            intro_text = response.text.strip()
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")

        # Validate length
        if len(intro_text) < 10:
            logger.warning(f"Generated intro too short ({len(intro_text)} chars), using title")
            return title

        if len(intro_text) > 150:
            logger.warning(f"Generated intro too long ({len(intro_text)} chars), truncating")
            intro_text = intro_text[:147] + "..."

        logger.info(f"Generated intro ({len(intro_text)} chars): {intro_text}")
        return intro_text

    except Exception as e:
        logger.error(f"LLM generation failed: {e}, falling back to title")
        return title
