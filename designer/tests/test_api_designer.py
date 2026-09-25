"""AnthropicDesigner against a fake client: no network, no spend.  Covers the
request shape (cached system prompt, settings in the user turn, effort),
usage/cost accounting, fix rounds, truncation, refusal and the cost cap."""
import os
from types import SimpleNamespace as NS

import pytest

from brickforge_designer import pipeline
from brickforge_designer.pipeline import AnthropicDesigner, DesignerError, cost, generate, system_prompt

SPECS = os.path.join(os.path.dirname(__file__), "..", "specs")
GOOD = open(os.path.join(SPECS, "pickup.bfd"), encoding="utf-8").read()
LOOSE = "model t\nbaseplate 0 0 green\npart 3001 red 4 4 9\n"


def reply(text, stop="end_turn", out=500, cache_write=0, cache_read=0, inp=40):
    return NS(content=[NS(type="thinking", thinking=""), NS(type="text", text=text)], stop_reason=stop,
              stop_details=NS(category="cyber") if stop == "refusal" else None,
              usage=NS(input_tokens=inp, output_tokens=out, cache_creation_input_tokens=cache_write,
                       cache_read_input_tokens=cache_read))


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = self

    def stream(self, **kw):
        # snapshot: the designer appends to its message list after the call
        self.calls.append(dict(kw, messages=list(kw["messages"])))
        r = self.replies.pop(0)

        class Ctx:
            def __enter__(s):
                return NS(get_final_message=lambda: r)

            def __exit__(s, *a):
                return False
        return Ctx()


def test_request_shape_caches_the_system_prompt_and_sends_settings_in_the_user_turn():
    fake = FakeClient([reply(GOOD, cache_write=2500)])
    r = generate("a red pickup truck", AnthropicDesigner(client=fake), sideways="off", size=20)
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"effort": "medium"}
    assert "thinking" not in call                      # always on for Opus 5.5; budget_tokens would 400
    assert call["system"] == [{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}]
    assert call["messages"] == [{"role": "user", "content": "Prompt: a red pickup truck\nSettings: sideways=off size=20"}]
    assert r["problems"] == [] and r["rounds"] == 0


def test_usage_and_cost_are_recorded_from_the_api_usage_fields():
    fake = FakeClient([reply(GOOD, out=1000, cache_write=2000, inp=50)])
    r = generate("pickup", AnthropicDesigner(client=fake))
    t = r["totals"]
    assert (t["calls"], t["input"], t["output"], t["cache_write"], t["cache_read"]) == (1, 50, 1000, 2000, 0)
    assert t["cost_usd"] == pytest.approx((50 * 4 + 1000 * 20 + 2000 * 5) / 1e6, abs=1e-4)


def test_checker_report_goes_back_and_a_fixed_spec_passes():
    fake = FakeClient([reply(LOOSE), reply("```\n" + GOOD + "```", cache_read=2000)])
    r = generate("pickup", AnthropicDesigner(client=fake))
    assert r["problems"] == [] and r["rounds"] == 1
    second = fake.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[1]["content"][0].type == "thinking"   # replayed unchanged (append-only)
    assert "LOOSE" in second[2]["content"]


def test_still_failing_after_fix_rounds_returns_problems_not_an_exception():
    fake = FakeClient([reply(LOOSE)] * 3)
    r = generate("x", AnthropicDesigner(client=fake))
    assert r["rounds"] == 2 and r["problems"]
    assert len(fake.calls) == 3


def test_truncated_reply_is_reported_to_the_model_then_fixed():
    fake = FakeClient([reply(GOOD[:30], stop="max_tokens"), reply(GOOD)])
    r = generate("pickup", AnthropicDesigner(client=fake))
    assert r["problems"] == [] and r["rounds"] == 1
    assert "cut off" in fake.calls[1]["messages"][-1]["content"]


def test_refusal_raises_a_user_safe_error():
    fake = FakeClient([reply("", stop="refusal")])
    with pytest.raises(DesignerError) as e:
        generate("x", AnthropicDesigner(client=fake))
    assert "different" in e.value.user_message


def test_cost_cap_stops_before_a_call_that_could_exceed_it():
    with pytest.raises(DesignerError, match="cost cap"):
        generate("x", AnthropicDesigner(client=FakeClient([]), cost_cap_usd=0.05))


def test_cost_cap_limits_fix_rounds_and_keeps_the_last_spec(monkeypatch):
    # first call spends almost the whole cap; the fix round must not start
    fake = FakeClient([reply(LOOSE, out=40000)])
    r = generate("x", AnthropicDesigner(client=fake, cost_cap_usd=0.85))
    assert len(fake.calls) == 1 and r["problems"] and r["rounds"] == 0


def test_max_tokens_shrinks_as_the_cap_gets_close():
    d = AnthropicDesigner(client=FakeClient([]), cost_cap_usd=0.30)
    d.system, d.messages = system_prompt(), [{"role": "user", "content": "Prompt: x"}]
    n = d._max_tokens()
    assert 4000 <= n < pipeline.CONFIG["max_tokens"]
    assert n * 20 / 1e6 < 0.30


def test_cost_is_zero_without_a_model():
    assert cost({"input": 100}, None) == 0.0


def test_reference_image_goes_first_in_the_design_message_only():
    fake = FakeClient([reply(LOOSE), reply(GOOD)])
    r = generate("pickup", AnthropicDesigner(client=fake), reference_image=(b"\x89PNGfake", "image/png"))
    first = fake.calls[0]["messages"][0]["content"]
    assert first[0]["type"] == "image" and first[0]["source"]["media_type"] == "image/png"
    assert first[1]["type"] == "text" and first[1]["text"].startswith("Prompt: pickup")
    # the fix round keeps the same first message (image included, served from
    # the conversation history) and only appends a text report
    assert fake.calls[1]["messages"][0]["content"] == first
    assert isinstance(fake.calls[1]["messages"][-1]["content"], str)
    assert r["problems"] == []
