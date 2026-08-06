"""Server-side content filter for prompts, run before any image generation
happens -- specifically before spending money on gpt-image-1, and before
the pipeline ever produces something sellable.

Two checks, deliberately for two different concerns -- do not conflate
them:
- OpenAI's moderation endpoint: genuine safety categories (harassment,
  hate, illicit, self-harm, sexual, violence, and subcategories -- 13
  flags in total). Verified directly against OpenAI's own docs before
  writing this, not assumed: it does NOT cover copyright or trademark at
  all. OpenAI routes IP disputes through separate manual report forms,
  not automated moderation.
- A maintained blocklist of well-known copyrighted characters/franchises:
  the actual mechanism for the real concern here. Selling build
  instructions for Pikachu is a genuine legal exposure that has nothing to
  do with "safety" in the moderation sense -- the mesh/TRELLIS pipeline's
  MIT licence covers the model, not whatever subject a user prompts for.

Deliberately conservative, per the explicit request this was built
against: a false rejection is mildly annoying, a false acceptance is a
takedown notice.
"""
from __future__ import annotations

import logging
import os
import re

import requests

logger = logging.getLogger("content_filter")

# Not exhaustive -- can't be. A maintained starting point covering the
# franchises most likely to actually get prompted (major game/movie/TV
# IP), meant to grow as false negatives turn up in the rejection log this
# module writes (see check_prompt). Matched with word boundaries against a
# lowercased prompt; a franchise name alone is enough to reject, not just
# specific character names, since "a Pokemon-style creature" still trades
# on the IP.
BLOCKED_TERMS = {
    # Pokemon
    "pokemon", "pikachu", "charizard", "bulbasaur", "squirtle", "eevee",
    "mewtwo", "snorlax", "jigglypuff",
    # Star Wars
    "star wars", "baby yoda", "grogu", "darth vader", "yoda", "chewbacca",
    "mandalorian", "stormtrooper", "millennium falcon",
    # Disney / Pixar
    "mickey mouse", "minnie mouse", "donald duck", "goofy", "elsa",
    "frozen", "moana", "simba", "lion king", "woody", "buzz lightyear",
    "toy story", "cinderella", "ariel", "ursula", "stitch",
    # Marvel
    "spider-man", "spiderman", "iron man", "captain america", "hulk",
    "thor", "avengers", "thanos", "black panther", "wolverine", "deadpool",
    # DC
    "batman", "superman", "wonder woman", "joker", "harley quinn",
    # Nintendo (non-Pokemon)
    "mario", "luigi", "bowser", "zelda", "link", "kirby", "yoshi",
    "donkey kong", "metroid", "samus",
    # Other well-known game/anime IP
    "sonic the hedgehog", "pac-man", "naruto", "goku", "dragon ball",
    "hello kitty", "minecraft steve", "among us",
}

_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("IMAGE_GEN_API_KEY")


def _check_blocklist(prompt: str) -> str | None:
    """Returns the matched term if the prompt references a known
    copyrighted franchise/character, else None."""
    normalized = prompt.lower()
    for term in BLOCKED_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", normalized):
            return term
    return None


def _check_openai_moderation(prompt: str) -> str | None:
    """Returns a comma-separated list of flagged categories if OpenAI's
    moderation endpoint flags this prompt, else None. Fails open (returns
    None, logs a warning) if no API key is configured or the request
    itself errors -- a moderation-endpoint outage should not block every
    prompt submission, and this is the supplementary safety check, not
    the primary mechanism for the copyright concern above."""
    if not _OPENAI_API_KEY:
        logger.warning("content_filter: no OpenAI API key configured, skipping moderation check")
        return None

    try:
        response = requests.post(
            "https://api.openai.com/v1/moderations",
            headers={"Authorization": f"Bearer {_OPENAI_API_KEY}"},
            json={"input": prompt},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()["results"][0]
    except Exception as exc:  # noqa: BLE001 -- fail open, log, don't block submission on an outage
        logger.warning("content_filter: OpenAI moderation check failed, skipping: %s", exc)
        return None

    if not result.get("flagged"):
        return None
    flagged_categories = [cat for cat, is_flagged in result.get("categories", {}).items() if is_flagged]
    return ", ".join(flagged_categories) or "flagged"


def check_prompt(prompt: str) -> tuple[bool, str | None]:
    """Returns (is_allowed, user_facing_message_if_rejected). Checks the
    blocklist first since it's free and instant; only calls out to OpenAI
    if that passes."""
    blocked_term = _check_blocklist(prompt)
    if blocked_term:
        logger.warning("content_filter REJECTED (blocklist match: %r): %r", blocked_term, prompt)
        return False, (
            "This prompt appears to reference a copyrighted character or franchise. "
            "Try describing an original creation instead."
        )

    flagged_categories = _check_openai_moderation(prompt)
    if flagged_categories:
        logger.warning("content_filter REJECTED (moderation: %s): %r", flagged_categories, prompt)
        return False, "This prompt violates our content policy. Please try a different description."

    return True, None
