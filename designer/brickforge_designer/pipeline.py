"""Prompt -> brick model, with a language model as the designer.

    1. compact design language      the model writes a short .bfd spec, never code (dsl.py)
    2. craft lives in the engine    slopes, tiles, SNOT anchors, eyes, hidden-cell colours (dsl.py)
    3. engine self-repair           verified retries in the engine; model sees only what's left
    4. capped reasoning             CONFIG["effort"] (Opus 5.5 thinking is always on; effort is the dial)
    5. hard cost / time caps        CONFIG["cost_cap_usd"], CONFIG["max_seconds"]
    6. design reuse                 DesignCache (optional)

`AnthropicDesigner` calls the Claude API; `FileDesigner` reads a spec from
disk instead, so the engine can be exercised without API calls.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter

from .dsl import Interp

HERE = os.path.dirname(os.path.abspath(__file__))

CONFIG = {
    "designer_model": "claude-opus-5-5",
    # Opus 5.5 always thinks; effort is the only control (its default is "medium").
    "effort": "medium",
    "max_fix_rounds": 2,                     # model-side rounds, after engine self-repair
    # Per-call ceiling on thinking + reply.  Specs are ~40-900 tokens; the rest is
    # thinking headroom.  Lowered automatically when the job's cost cap is close.
    "max_tokens": 32000,
    "cost_cap_usd": 1.00,                    # hard per-job ceiling, all calls included
    "max_seconds": 420,                      # no new fix round starts after this
    "request_timeout_s": 150,
    "max_retries": 1,                        # SDK retries 429/5xx/connection errors
    "max_spec_chars": 20000,
    # Loose groups this small are removed (and recorded) instead of failing
    # the model; 0 disables.  See prune_tiny_loose.
    "prune_loose_max_parts": 3,
    "prune_loose_max_share": 0.02,
    # Hard output limits, checked like any other problem (a 32x32 baseplate
    # plus roof overhang / a vehicle parked alongside).
    "limits": {"max_parts": 2500, "max_span_studs": 40},
    # $ per million tokens (Claude API, Sep 2026).
    "prices": {"claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_write": 5.0, "cache_read": 0.20}},
}


class DesignerError(Exception):
    """A design could not be produced (API failure, refusal, cost cap, bad
    reply).  `user_message` is safe to show; str(e) is for logs."""

    def __init__(self, log_message, user_message="The designer could not produce a model. Please try again."):
        super().__init__(log_message)
        self.user_message = user_message


def system_prompt():
    with open(os.path.join(HERE, "PROMPT.md"), encoding="utf-8") as f:
        return f.read()


def user_message(prompt, sideways="auto", size=24):
    """Per-request settings go in the user turn so the cached system prompt
    stays byte-identical across requests.  `finish` is engine-only (the
    model's spec is the same either way), so it is not sent."""
    return f"Prompt: {prompt.strip()}\nSettings: sideways={sideways} size={int(size)}"


# ---------------------------------------------------------------- design cache
class DesignCache:
    """Reuse a spec for a near-identical prompt with the same settings."""

    def __init__(self, path=os.path.join(HERE, "..", ".design_cache.json")):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    @staticmethod
    def words(prompt):
        stop = {"a", "an", "the", "me", "and", "with", "of", "lego", "please", "i", "want", "it", "to", "in", "for"}
        return {w for w in re.findall(r"[a-z]+", prompt.lower()) if w not in stop}

    @staticmethod
    def _tag(sideways, size):
        return f"@sideways={sideways},size={int(size)}"

    def lookup(self, prompt, sideways="auto", size=24, threshold=0.8):
        w, tag = self.words(prompt), self._tag(sideways, size)
        best = None
        for key, spec in self.data.items():
            words, _, ktag = key.partition(" @")
            if "@" + ktag != tag:
                continue
            kw = set(words.split())
            score = len(w & kw) / max(1, len(w | kw))
            if score >= threshold and (best is None or score > best[0]):
                best = (score, spec)
        return best[1] if best else None

    def store(self, prompt, spec, sideways="auto", size=24):
        self.data[" ".join(sorted(self.words(prompt))) + " " + self._tag(sideways, size)] = spec
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f)


# ---------------------------------------------------------------- designers
class FileDesigner:
    """Stands in for the API: the spec was written by a person/Claude session.
    Usage figures come from a sidecar <spec>.usage.json if present."""

    model = None

    def __init__(self, spec_path):
        self.spec_path = spec_path

    def design(self, prompt, system, settings, reference_image=None):
        with open(self.spec_path, encoding="utf-8") as f:
            spec = f.read()
        usage = {}
        side = self.spec_path.rsplit(".", 1)[0] + ".usage.json"
        if os.path.exists(side):
            with open(side, encoding="utf-8") as f:
                usage = json.load(f)
        return spec, usage

    def fix(self, report):
        return None, {}


def extract_spec(text):
    """The reply should be the spec alone; tolerate a Markdown code fence."""
    m = re.search(r"```[a-zA-Z]*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def api_available():
    """Detailed mode is off (not crashing) when no key is configured."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


IMAGE_TOKENS = 1600      # a ~1024px image costs about w*h/750 input tokens; rounded up for the cost cap


class AnthropicDesigner:
    """Claude API designer.  System = PROMPT.md with a cache breakpoint; user =
    prompt + settings; fix rounds append the checker report to the same
    conversation (append-only, thinking blocks replayed unchanged, so the
    cached prefix stays valid).  Tracks spend and refuses to start a call
    that could push the job past `cost_cap_usd`."""

    def __init__(self, client=None, model=None, effort=None, cost_cap_usd=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic(timeout=CONFIG["request_timeout_s"], max_retries=CONFIG["max_retries"])
        self.client = client
        self.model = model or CONFIG["designer_model"]
        self.effort = effort or CONFIG["effort"]
        self.cost_cap = CONFIG["cost_cap_usd"] if cost_cap_usd is None else cost_cap_usd
        self.spent = 0.0
        self.replayed_tokens = 0
        self.system = None
        self.messages = []

    def design(self, prompt, system, settings, reference_image=None):
        """`reference_image`: optional (bytes, media_type), e.g. a generated
        picture of the subject, sent ahead of the prompt text."""
        self.system = system
        self.replayed_tokens = 0
        text = user_message(prompt, settings.get("sideways", "auto"), settings.get("size", 24))
        if reference_image is not None:
            import base64
            data, media_type = reference_image
            content = [{"type": "image", "source": {"type": "base64", "media_type": media_type,
                                                    "data": base64.standard_b64encode(data).decode("ascii")}},
                       {"type": "text", "text": text + "\nReference image attached."}]
            self.replayed_tokens = IMAGE_TOKENS
            self.messages = [{"role": "user", "content": content}]
        else:
            self.messages = [{"role": "user", "content": text}]
        return self._call()

    def fix(self, report):
        self.messages.append({"role": "user", "content": f"Checker report:\n{report}\n\nReply with the whole corrected spec."})
        return self._call()

    def _max_tokens(self):
        p = CONFIG["prices"][self.model]
        # pessimistic: text at ~3 chars/token, earlier replies (thinking included, replayed
        # as input) at their measured output size, and everything billed as a cache write
        tokens = (len(self.system) + sum(len(m["content"]) for m in self.messages if isinstance(m["content"], str))) / 3
        tokens += self.replayed_tokens
        worst_input = tokens * p["cache_write"] / 1e6
        room = self.cost_cap - self.spent - worst_input
        n = min(CONFIG["max_tokens"], int(room / p["output"] * 1e6))
        if n < 4000:
            raise DesignerError(f"cost cap ${self.cost_cap:.2f} reached (spent ${self.spent:.3f})")
        return n

    def _call(self):
        import anthropic
        max_tokens = self._max_tokens()
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
                output_config={"effort": self.effort},
                messages=self.messages,
            ) as stream:
                resp = stream.get_final_message()
        except anthropic.RateLimitError as e:
            raise DesignerError(f"rate limited: {e}", "The designer is busy right now. Please try again shortly.")
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError,
                anthropic.BadRequestError) as e:
            raise DesignerError(f"API configuration error: {e}")
        except anthropic.APIStatusError as e:
            raise DesignerError(f"API error {e.status_code}: {e}", "The designer is busy right now. Please try again shortly.")
        except anthropic.APIConnectionError as e:     # includes timeouts
            raise DesignerError(f"API connection error: {e}", "The designer is busy right now. Please try again shortly.")
        u = resp.usage
        usage = {"input": u.input_tokens, "output": u.output_tokens,
                 "cache_write": u.cache_creation_input_tokens or 0, "cache_read": u.cache_read_input_tokens or 0,
                 "stop_reason": resp.stop_reason, "request_id": getattr(resp, "_request_id", None)}
        self.spent += cost(usage, self.model)
        self.messages.append({"role": "assistant", "content": resp.content})
        self.replayed_tokens += u.output_tokens
        if resp.stop_reason == "refusal":
            raise DesignerError(f"model refused ({getattr(resp.stop_details, 'category', None)})",
                                "That prompt can't be designed. Please try a different one.")
        text = "".join(b.text for b in resp.content if b.type == "text")
        if resp.stop_reason == "max_tokens":
            return None, dict(usage, truncated=True)
        return extract_spec(text), usage


# ---------------------------------------------------------------- build + checks
def build(spec_text, finish="tiled", sideways="auto"):
    it = Interp(finish=finish, sideways=sideways)
    D = it.run(spec_text)
    prune_tiny_loose(D, it)
    return D, it


def prune_tiny_loose(D, it):
    """Loose groups of a few parts (a 1x1 tile and the plate under it at the
    rim of a round overhang) would fall off a real build; remove them rather
    than fail the whole model.  Bounded so it can never hide a real failure:
    only groups of <= prune_loose_max_parts, and at most prune_loose_max_share
    of the model in total.  Always recorded in the engine repairs."""
    n_max, share = CONFIG["prune_loose_max_parts"], CONFIG["prune_loose_max_share"]
    if not n_max or not D.parts:
        return 0
    comps, _ = D.components()
    tiny = [c for _, status, c, _ in classify_pieces(D, comps) if status == "loose" and len(c) <= n_max]
    drop = [i for c in tiny for i in c]
    if not drop or len(drop) > share * len(D.parts):
        return 0
    D.remove(drop)
    it.repairs.append(("pruned tiny loose groups", len(drop)))
    return len(drop)


TILE_IDS = {"3070b", "3069b", "63864", "2431", "3068b", "87079", "6636", "4162", "98138"}
CURVED_IDS = {"11477", "15068", "93273", "49307", "54200", "85984", "50950", "61678", "24309", "93606",
              "24201", "13547"}
MIN_STANDING_PARTS = 20        # a separate piece this big that rests on something is a real sub-build


def _surface(pid):
    if pid in TILE_IDS:
        return "tiles"
    if pid in CURVED_IDS:
        return "curved slopes"
    return "parts"


def resting_contacts(D, comp):
    """Parts outside `comp` whose top face touches the underside of a part in
    `comp`, with the xz rectangle of each contact (LDU)."""
    inside = set(comp)
    out = []
    for n in comp:
        q = D.parts[n]
        (x0, x1), (_, yb), (z0, z1) = q.box
        for key in D._buckets(((x0, x1), (yb, yb + 1), (z0, z1))):
            for m in D._hash.get(key, ()):
                if m in inside:
                    continue
                p = D.parts[m]
                if abs(p.box[1][0] - yb) > 1:
                    continue
                ix0, ix1 = max(x0, p.box[0][0]), min(x1, p.box[0][1])
                iz0, iz1 = max(z0, p.box[2][0]), min(z1, p.box[2][1])
                if ix1 - ix0 > 1 and iz1 - iz0 > 1:
                    out.append((m, (ix0, ix1, iz0, iz1)))
    return out


def table_level(D):
    """LDraw y of the table: the underside of the model's lowest part (a
    baseplate or base when there is one, else the model's own feet)."""
    return max((q.box[1][1] for q in D.parts), default=0.0)


def table_contacts(D, comp, tol=1.0):
    """A piece whose lowest parts are at table level rests on the table: its
    contacts are those parts' footprints (xz rectangles, LDU), with no part
    under them (None)."""
    yb = max(D.parts[n].box[1][1] for n in comp)
    if abs(yb - table_level(D)) > tol:
        return []
    return [(None, (D.parts[n].box[0][0], D.parts[n].box[0][1], D.parts[n].box[2][0], D.parts[n].box[2][1]))
            for n in comp if abs(D.parts[n].box[1][1] - yb) <= tol]


def _centre_of_mass(D, comp):
    tot = cx = cz = 0.0
    for n in comp:
        (x0, x1), (y0, y1), (z0, z1) = D.parts[n].box
        v = max(1.0, (x1 - x0) * (y1 - y0) * (z1 - z0))
        tot, cx, cz = tot + v, cx + v * (x0 + x1) / 2, cz + v * (z0 + z1) / 2
    return cx / tot, cz / tot


def _hull(points):
    """Convex hull, counter-clockwise (monotone chain)."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _stands_steady(D, comp, contacts, margin=5.0):
    """Centre of mass (by box volume) over the support area: the convex hull
    of the rectangles it rests on, grown by `margin` LDU."""
    cx, cz = _centre_of_mass(D, comp)
    pts = [(x, z) for _, (x0, x1, z0, z1) in contacts
           for x in (x0 - margin, x1 + margin) for z in (z0 - margin, z1 + margin)]
    hull = _hull(pts)
    return all((b[0] - a[0]) * (cz - a[1]) - (b[1] - a[1]) * (cx - a[0]) >= -1e-6
               for a, b in zip(hull, hull[1:] + hull[:1]))


def classify_pieces(D, comps):
    """Per assembly: the grounded piece (the one holding its lowest part),
    separate pieces that genuinely stand on something (accepted: like a car
    parked on a road, they are their own sub-build), and loose groups.  A
    model with no base stands on the table: a separate piece whose feet are
    at table level stands on it, like one resting on the model.  The main
    piece's contacts are its table footprint (empty when it is held above
    the table, e.g. a vehicle's body on its tyres)."""
    out = []
    by_asm = {}
    for c in comps:
        by_asm.setdefault(D.parts[c[0]].asm, []).append(c)
    for asm, pieces in by_asm.items():
        ground = max(pieces, key=lambda c: (max(D.parts[n].box[1][1] for n in c), len(c)))
        for c in pieces:
            if c is ground:
                out.append((asm, "main", c, table_contacts(D, c)))
                continue
            contacts = resting_contacts(D, c) or table_contacts(D, c)
            if len(c) >= MIN_STANDING_PARTS and contacts and _stands_steady(D, c, contacts):
                out.append((asm, "standing", c, contacts))
            else:
                out.append((asm, "loose", c, contacts))
    return out


def _loose_report(D, asm, c, contacts):
    srcs = Counter(D.parts[n].src for n in c if D.parts[n].src is not None)
    src = f" from line {srcs.most_common(1)[0][0]}" if srcs else ""
    low = max(c, key=lambda n: D.parts[n].box[1][1])
    q = D.parts[low]
    where = f"x={round(q.box[0][0] / 20)} z={round(q.box[2][0] / 20)} level={round(-q.box[1][1] / 8)}"
    if not contacts:
        why = "nothing is underneath it (it floats); lower it onto studs or extend it into its neighbour"
    elif len(c) >= MIN_STANDING_PARTS:
        why = "it would tip over; move it so its weight is over what it stands on, or widen its base"
    elif all(m is None for m, _ in contacts):
        why = ("it stands on the table by itself, not connected to the model; join it to the model "
               "(or use a base if the subject needs a setting)")
    else:
        under = Counter(_surface(D.parts[m].pid) for m, _ in contacts)
        lines = sorted({D.parts[m].src for m, _ in contacts if D.parts[m].src is not None})
        what = " and ".join(k for k, _ in under.most_common())
        on = f" (line {', '.join(map(str, lines))})" if lines else ""
        why = (f"it only rests on {what}{on} without clicking onto studs; merge it into the shape next to it, "
               f"or remove it")
    return f"LOOSE {asm}: {len(c)} part(s){src} near {where}: {why}"


def check(D, it):
    comps, _ = D.components()
    by_asm = Counter(q.asm for q in D.parts)
    problems = []
    pieces = classify_pieces(D, comps)
    for asm, status, c, contacts in pieces:
        if status == "loose" and len([p for p in problems if p.startswith("LOOSE")]) < 6:
            problems.append(_loose_report(D, asm, c, contacts))
        elif status == "main" and contacts and not _stands_steady(D, c, contacts, margin=0):
            what = "the model" if asm == "main" else asm
            problems.append(f"TIPS {asm}: {what} would tip over on the table: its weight is outside the "
                            f"feet it stands on; widen or move its feet/legs under its weight, or balance it")
    for (m, n) in D.collisions()[:8]:
        a, b = D.parts[m], D.parts[n]
        problems.append(f"COLLISION {a.pid} ({a.tag or '-'}) with {b.pid} ({b.tag or '-'}) near cell "
                        f"x={round(a.pos[0]) // 20} z={round(a.pos[2]) // 20}")
    below = [q for q in D.parts if q.box[1][1] > 1]
    if below:
        lines = sorted({q.src for q in below if q.src is not None})
        problems.append(f"BELOW: {len(below)} part(s)" + (f" from line {', '.join(map(str, lines))}" if lines else "")
                        + " go below level 0 (the table, or the baseplate's top); raise them")
    lim = CONFIG["limits"]
    if len(D.parts) > lim["max_parts"]:
        problems.append(f"TOO BIG: {len(D.parts)} parts (limit {lim['max_parts']}); make the model smaller")
    main = [q for q in D.parts if q.pid != "3811"]
    if main:
        span = max(max(q.box[a][1] for q in main) - min(q.box[a][0] for q in main) for a in (0, 2)) / 20
        if span > lim["max_span_studs"]:
            problems.append(f"TOO BIG: spans {span:.0f} studs (limit {lim['max_span_studs']}); "
                            f"keep everything within a 32x32 baseplate")
    problems = [f"SPEC {e}" for e in it.errors] + problems
    stats = {"parts": len(D.parts), "assemblies": dict(by_asm), "components": len(comps),
             "pieces": [{"assembly": a, "status": s, "parts": len(c)} for a, s, c, _ in pieces],
             "engine_repairs": it.repairs, "problems": len(problems)}
    return problems, stats


def bom(D):
    return Counter((q.pid, q.color) for q in D.parts)


# ---------------------------------------------------------------- token estimates
def estimate_tokens(text):
    """Rough Claude-token estimate for spec-like text: words, numbers and
    punctuation runs each count; long words split.  Real numbers come from
    the API's usage fields."""
    n = 0
    for tok in re.findall(r"[A-Za-z_]+|\d+|\.\.|[^\sA-Za-z_\d]", text):
        n += 1 + (len(tok) - 1) // 6 if tok.isalpha() or "_" in tok else 1
    return n


def cost(usage, model):
    if not model:
        return 0.0
    p = CONFIG["prices"][model]
    return (usage.get("input", 0) * p["input"] + usage.get("output", 0) * p["output"]
            + usage.get("cache_write", 0) * p["cache_write"] + usage.get("cache_read", 0) * p["cache_read"]) / 1e6


def usage_totals(usage_log, model):
    tot = {"calls": 0, "input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    for _, u in usage_log:
        if u:
            tot["calls"] += 1
            for k in ("input", "output", "cache_write", "cache_read"):
                tot[k] += u.get(k, 0)
    tot["cost_usd"] = round(cost(tot, model), 4)
    return tot


# ---------------------------------------------------------------- pipeline
def generate(prompt, designer, out_dir=None, cache=None, name=None, finish="tiled", sideways="auto", size=24,
             on_phase=None, reference_image=None):
    """Design -> build -> check -> up to max_fix_rounds of model repairs.
    Raises DesignerError when no spec can be obtained at all; otherwise
    returns the result with `problems` (empty = passed every check)."""
    system = system_prompt()
    settings = {"sideways": sideways, "size": size}
    t0 = time.time()
    usage_log = []
    spec = cache.lookup(prompt, sideways, size) if cache else None
    if spec is None:
        spec, usage = designer.design(prompt, system, settings, reference_image=reference_image)
        usage_log.append(("design", usage))
    else:
        usage_log.append(("cache hit", {}))
    if on_phase:
        on_phase("building")
    rounds = 0
    D = it = None
    cur, spec, stats = spec, None, {}
    while True:
        if cur is None:                     # reply hit max_tokens: keep the last built spec, if any
            problems = ["SPEC your reply was cut off before the spec was finished; write a shorter spec"]
        elif len(cur) > CONFIG["max_spec_chars"]:
            problems = [f"SPEC spec is {len(cur)} characters (limit {CONFIG['max_spec_chars']}); simplify it"]
        else:
            spec = cur
            D, it = build(spec, finish, sideways)
            problems, stats = check(D, it)
        if not problems or rounds >= CONFIG["max_fix_rounds"] or time.time() - t0 > CONFIG["max_seconds"]:
            break
        if on_phase:
            on_phase("fixing")
        try:
            new, usage = designer.fix("\n".join(problems))
        except DesignerError:
            if D is None:
                raise
            break                               # keep the best spec so far; it fails the checks below
        if new is None and not usage:
            break                               # FileDesigner: no model to ask
        rounds += 1
        usage_log.append((f"fix {rounds}", usage))
        cur = new
    if D is None:
        raise DesignerError(f"designer never produced a usable spec: {problems[:1]}")
    ldr = D.ldr()
    path = None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{name or D.title}.ldr")
        with open(path, "w", encoding="utf-8") as f:
            f.write(ldr)
    if cache and not problems:
        cache.store(prompt, spec, sideways, size)
    model = getattr(designer, "model", None)
    return dict(path=path, ldr=ldr, design=D, problems=problems, stats=stats, rounds=rounds, usage=usage_log,
                totals=usage_totals(usage_log, model), seconds=round(time.time() - t0, 1), spec=spec,
                system=system)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build a spec file, or (--api) design one from a prompt.")
    ap.add_argument("spec", nargs="?", help=".bfd spec file (omit with --api)")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--api", action="store_true", help="design with the Claude API from --prompt")
    ap.add_argument("--name")
    ap.add_argument("--finish", default="tiled", choices=("tiled", "studs"))
    ap.add_argument("--sideways", default="auto", choices=("off", "auto", "more"))
    ap.add_argument("--size", type=int, default=24)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "out"))
    a = ap.parse_args()
    designer = AnthropicDesigner() if a.api else FileDesigner(a.spec)
    name = a.name or (os.path.basename(a.spec).rsplit(".", 1)[0] if a.spec else "api_model")
    r = generate(a.prompt, designer, a.out, name=name, finish=a.finish, sideways=a.sideways, size=a.size)
    print(f"wrote {r['path']}  ({r['seconds']}s, {r['rounds']} fix rounds)")
    print("stats:", json.dumps(r["stats"]))
    print("problems:" if r["problems"] else "problems: none")
    for p in r["problems"]:
        print("  ", p)
    print("usage:", json.dumps(r["totals"]))
    if a.api:
        with open(os.path.join(a.out, f"{name}.bfd"), "w", encoding="utf-8") as f:
            f.write(r["spec"])
    spec_tok, sys_tok = estimate_tokens(r["spec"]), estimate_tokens(r["system"])
    print(f"spec ~{spec_tok} tokens ({len(r['spec'])} chars), system prompt ~{sys_tok} tokens")
