"""Classifies a user's prompt as "organic" (animals, food, plants,
landscapes, creatures -- natural asymmetry is expected and part of the
subject, so a legalized model's own asymmetry should be left alone) or
"ordered" (vehicles, buildings, furniture, mechanical objects -- a
person expects these to be built flush and symmetric, and a real
generated model that's "close to symmetric but not exactly" reads as
messy rather than natural).

Deliberately a plain keyword classifier, not an LLM call: this decision
sits directly in the generation critical path (see jobs.py::process_job),
and a wrong/unavailable model name for a cheap classification call would
be a needless new failure mode for a decision that already has a second,
independent safety net downstream -- brickforge.pipeline.symmetry's own
`detect_mirror_plane` requires the model to already measure as close to
symmetric (score >= 0.85 by default) before it enforces anything, so a
prompt this classifier gets wrong ("ordered" for something that isn't)
still can't force a bad mirror onto a shape that was never symmetric to
begin with -- it just no-ops. Given that safety net, a fast, zero-cost,
zero-new-dependency heuristic is the right tool here, not another
external API call.

Unknown prompts default to "organic" (the safe default): symmetry
enforcement is a "want to look right" feature, and failing to apply it
to a genuinely ordered subject the classifier didn't recognize is a
missed cosmetic improvement, not a broken build -- the opposite mistake
(forcing symmetry onto something never meant to be symmetric) is the
one this default is chosen to avoid.
"""

from __future__ import annotations

import re

# Not exhaustive -- a representative set per the founder's own examples
# ("vehicles/buildings" for ordered, "animals, food, landscapes" for
# organic), reviewed and extended with obvious neighbors of each
# category. Checked with word-boundary matching (see _classify below),
# not bare substring search, so e.g. "car" doesn't match "carrot".
_ORDERED_KEYWORDS = frozenset(
    {
        "car", "truck", "van", "bus", "vehicle", "motorcycle", "bike", "bicycle",
        "plane", "airplane", "jet", "aircraft", "helicopter", "rocket", "spaceship",
        "ship", "boat", "submarine", "yacht",
        "train", "locomotive", "tram", "trolley",
        "house", "building", "tower", "castle", "skyscraper", "bridge", "church",
        "cathedral", "mansion", "cabin", "lighthouse", "windmill", "barn", "warehouse",
        "robot", "mech", "machine", "engine", "tank", "drone", "satellite",
        "chair", "table", "desk", "lamp", "shelf", "cabinet", "sofa", "couch", "bed",
        "computer", "laptop", "phone", "television", "tv", "radio", "camera",
        "gun", "cannon", "sword", "shield", "weapon", "rifle",
        "guitar", "piano", "clock", "watch",
    }
)

_ORGANIC_KEYWORDS = frozenset(
    {
        "animal", "creature", "monster", "dragon", "dinosaur", "beast",
        "dog", "puppy", "cat", "kitten", "bird", "owl", "eagle", "fish", "shark",
        "whale", "dolphin", "octopus", "turtle", "frog", "snake", "lizard",
        "fox", "wolf", "bear", "lion", "tiger", "elephant", "giraffe", "horse",
        "rabbit", "bunny", "deer", "monkey", "panda", "penguin", "duck", "chicken",
        "spider", "butterfly", "bee", "insect", "bug",
        "person", "human", "man", "woman", "child", "baby", "face", "body",
        "tree", "flower", "plant", "leaf", "bush", "cactus", "mushroom",
        "fruit", "vegetable", "food", "cake", "bread", "pizza", "burger", "fruit",
        "mountain", "landscape", "hill", "cloud", "island", "cave", "rock",
        "snowman", "cloud", "wave",
    }
)


def _tokenize(prompt: str) -> set[str]:
    return set(re.findall(r"[a-z]+", prompt.lower()))


def classify_prompt(prompt: str) -> str:
    """Returns "ordered" or "organic". See module docstring for the
    reasoning behind the keyword approach and the "organic" default."""
    words = _tokenize(prompt)
    if words & _ORDERED_KEYWORDS:
        return "ordered"
    if words & _ORGANIC_KEYWORDS:
        return "organic"
    return "organic"
