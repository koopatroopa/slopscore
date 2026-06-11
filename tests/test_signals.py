"""Behavioural spec for the heuristic signal detectors.

Each test plants known content and asserts the detector reports it. The ground
truth (what was planted) is independent of the code under test.
"""

from slopscore.signals import Document, evaluate


def hits_by_name(doc):
    return {h.name: h for h in evaluate(doc)}


def test_assembled_joins_fields_with_blank_lines():
    doc = Document(title="T", body="B", commits=("c1", "c2"))
    assert doc.assembled == "T\n\nB\n\nc1\n\nc2"


def test_clean_human_text_fires_nothing():
    doc = Document(
        title="Fix off-by-one in pagination",
        body="The loop ran one past the end. Adjusted the bound and added a test.",
        commits=("Fix pagination bound",),
    )
    assert evaluate(doc) == []


def test_ai_self_reference_fires_on_attribution_and_phrase():
    a = hits_by_name(Document(body="Co-Authored-By: Claude <noreply@anthropic.com>"))
    assert "ai_self_reference" in a
    b = hits_by_name(Document(body="As an AI, I cannot run the tests here."))
    assert "ai_self_reference" in b


def test_ai_self_reference_catches_bracketed_claude_code_footer():
    # The DEFAULT Claude Code footer uses the bracketed/link form - the literal
    # phrase "generated with claude" can't match across the "[".
    d = Document(body="Improved perf.\n\nGenerated with [Claude Code](https://claude.ai/code)")
    assert "ai_self_reference" in hits_by_name(d)


def test_ai_self_reference_catches_copilot_coauthor():
    d = Document(commits=("Add util\n\nCo-authored-by: Copilot <copilot@github.com>",))
    assert "ai_self_reference" in hits_by_name(d)


def test_ai_self_reference_covers_common_ai_agent_trailers():
    # Pattern-spread: the population is AI-agent Co-Authored-By trailers, not just
    # claude/copilot. The well-known coding agents must be covered too.
    for agent in ("Cursor", "Codex", "Devin"):
        d = Document(commits=(f"Fix bug\n\nCo-authored-by: {agent} <noreply@example.com>",))
        assert "ai_self_reference" in hits_by_name(d), agent


def test_cliche_is_case_insensitive_and_word_bounded():
    fired = hits_by_name(Document(body="Let us Delve Into the design."))
    assert "ai_cliche_phrases" in fired
    # 'delved' must not match the literal phrase 'delve into'.
    quiet = hits_by_name(Document(body="We delved deeper yesterday."))
    assert "ai_cliche_phrases" not in quiet


def test_cliche_count_is_capped():
    body = (
        "It's worth noting this. At its core it works. In conclusion it ships. "
        "Needless to say, to put it simply, that being said."
    )
    h = hits_by_name(Document(body=body))["ai_cliche_phrases"]
    assert h.occurrences >= 4
    assert h.counted == h.cap  # capped
    assert h.contribution == h.weight * h.cap


def test_promotional_adjective_respects_word_boundary():
    fired = hits_by_name(Document(body="A robust, seamless solution."))
    assert "promotional_adjectives" in fired
    quiet = hits_by_name(Document(body="We measured its robustness empirically."))
    assert "promotional_adjectives" not in quiet


def test_sycophantic_opener_fires():
    assert "sycophantic_openers" in hits_by_name(Document(body="Certainly! Here is the change."))


def test_bold_lead_in_list_fires_on_pattern_not_inline_bold():
    fired = hits_by_name(Document(body="- **Setup:** install deps\n- **Run:** call main"))
    assert "bold_lead_in_lists" in fired
    quiet = hits_by_name(Document(body="This is **really** important to note."))
    assert "bold_lead_in_lists" not in quiet


def test_section_scaffolding_counts_template_headers():
    body = "## Overview\ntext\n## Testing\ntext\n## Summary\ntext"
    h = hits_by_name(Document(body=body))["section_scaffolding"]
    assert h.occurrences == 3


def test_em_dash_counts_only_u2014():
    # one em-dash, one en-dash, one ascii double-hyphen
    doc = Document(body="a — b – c -- d")
    h = hits_by_name(doc)["em_dash_density"]
    assert h.occurrences == 1


def test_emoji_density_fires_on_emoji_only():
    fired = hits_by_name(Document(body="Ship it \U0001f680 ✅"))
    assert "emoji_density" in fired
    assert "emoji_density" not in hits_by_name(Document(body="Ship it now."))


def test_contribution_is_weight_times_capped_count():
    # two em-dashes, weight 0.5, cap 6 -> counted 2 -> contribution 1.0
    h = hits_by_name(Document(body="a — b — c"))["em_dash_density"]
    assert h.counted == 2
    assert h.contribution == h.weight * 2


def test_curly_quotes_counted_em_dash_style():
    from slopscore.signals import _detect_curly_quotes

    n, _ = _detect_curly_quotes("a “quoted” phrase and it’s done")
    assert n == 3
    assert _detect_curly_quotes("plain 'ascii' \"quotes\"")[0] == 0


def test_negative_parallelism_matches_both_shapes():
    from slopscore.signals import _detect_negative_parallelism

    n, ev = _detect_negative_parallelism(
        "This is not just a refactor, but a rethink. "
        "It's not about speed, it's about craft."
    )
    assert n == 2
    assert any("not just" in e for e in ev)
    assert _detect_negative_parallelism("not only did we ship it")[0] == 0


def test_negative_parallelism_cross_sentence_and_anaphora():
    from slopscore.signals import _detect_negative_parallelism

    pivot = "Amazon isn't just buying content. They're buying credibility."
    inspirational = "This isn't just about AI. It's about humanity."
    anaphora = "Not for advertising. Not for distribution. For AI training."
    for text in (pivot, inspirational, anaphora):
        assert _detect_negative_parallelism(text)[0] >= 1, text
    assert _detect_negative_parallelism("The tests are not just slow.")[0] == 0


def test_rhetorical_qa_detects_self_answered_questions():
    from slopscore.signals import _detect_rhetorical_qa

    n, _ = _detect_rhetorical_qa(
        "Why? Because human credibility matters. What changed? The math did."
    )
    assert n == 2
    assert _detect_rhetorical_qa("What changed in this release is the parser.")[0] == 0


def test_vague_authority_phrases_fire():
    from slopscore.signals import SIGNALS

    detector = {s.name: s for s in SIGNALS}["vague_authority"].detector
    n, ev = detector("Studies show this works. Experts agree it is fine.")
    assert n == 2
    assert "studies show" in [e.lower() for e in ev]


def test_emoji_zwj_sequence_counts_as_one():
    from slopscore.signals import _detect_emoji

    # A person-coding emoji is one glyph: man + skin-tone + ZWJ + laptop.
    # Counting the components separately falsely inflated a real human commit
    # (gardener d0368438) to a FLAG. One glyph = one occurrence.
    assert _detect_emoji("Local Provider Extension 👨🏼‍💻 (#5115)")[0] == 1
    # Two distinct emoji still count as two.
    assert _detect_emoji("ship it 🚀🎉")[0] == 2
    # A skin-toned single emoji is still one.
    assert _detect_emoji("thumbs 👍🏽")[0] == 1
