"""LLM utilities — theme labeling, synthesis, and outreach generation."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_API_KEY not set")
        _client = OpenAI(api_key=api_key)
    return _client


def generate_theme_label(signal_texts: list[str], max_tokens: int = 50) -> str:
    """Generate a concise theme label from a cluster of signal texts.

    Args:
        signal_texts: Raw text from signals in the cluster.
        max_tokens: Max tokens for the response.

    Returns:
        A short theme label (e.g. "Neuromorphic edge inference").
    """
    combined = "\n".join(f"- {t[:200]}" for t in signal_texts[:10])

    response = _get_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a venture capital analyst. Given a cluster of technology signals, "
                    "generate a concise theme label (3-6 words) that captures the emerging trend. "
                    "Be specific and investment-relevant. Return only the label, nothing else."
                ),
            },
            {"role": "user", "content": f"Signals:\n{combined}"},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )

    label = response.choices[0].message.content.strip().strip('"')
    logger.info("Generated theme label: %s", label)
    return label


def synthesize_theme_description(
    label: str,
    signal_texts: list[str],
    signal_maturity: str,
    max_tokens: int = 300,
) -> str:
    """Generate an investment-grade theme description.

    Args:
        label: Theme label.
        signal_texts: Raw signal texts.
        signal_maturity: Current maturity classification.
        max_tokens: Max tokens for response.

    Returns:
        2-3 sentence investment thesis description.
    """
    combined = "\n".join(f"- {t[:200]}" for t in signal_texts[:8])

    response = _get_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a venture capital analyst writing for investment partners. "
                    "Synthesize the signals into a 2-3 sentence investment thesis. "
                    "Be specific about the opportunity, mention key players if evident, "
                    "and note the signal maturity. Write in investment-grade language."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Theme: {label}\n"
                    f"Signal Maturity: {signal_maturity}\n\n"
                    f"Signals:\n{combined}"
                ),
            },
        ],
        max_tokens=max_tokens,
        temperature=0.4,
    )

    return response.choices[0].message.content.strip()


def generate_founder_outreach(
    founder_name: str,
    signals_detected: list[str],
    theme_label: str | None = None,
    max_tokens: int = 200,
) -> str:
    """Generate a personalized draft outreach message for a founder.

    Args:
        founder_name: Founder's name.
        signals_detected: List of signal keys detected.
        theme_label: Related theme if known.
        max_tokens: Max response tokens.

    Returns:
        Draft outreach email text.
    """
    signal_descriptions = {
        "repeat_founder": "previously founded/exited a company",
        "twitter_bio_change_to_stealth": "recently changed their Twitter bio to suggest building something new",
        "ex_tier1_company_departure": "recently left a top-tier tech company",
        "published_paper_in_theme": "published research in a relevant area",
        "open_source_repo_created": "started a new open-source project",
        "github_contribution_spike": "showing increased technical activity",
    }

    signal_text = ", ".join(
        signal_descriptions.get(s, s) for s in signals_detected
    )

    response = _get_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a venture capital partner writing a warm outreach message to a "
                    "potential founder. Be authentic, specific about why you're reaching out, "
                    "and non-pushy. Keep it under 4 sentences. Don't use generic VC jargon."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Founder: {founder_name}\n"
                    f"Signals: {signal_text}\n"
                    f"Theme: {theme_label or 'General'}\n\n"
                    "Write a brief, personalized outreach message."
                ),
            },
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )

    return response.choices[0].message.content.strip()
