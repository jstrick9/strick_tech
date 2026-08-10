"""Module 12 regression tests — Information Hierarchy (Tier 1 / IVREN).

This module compiles the context block injected into every AI call, so a
defect here misinforms every agent in the platform.

1. Answering the guided interview with whitespace produced four files of empty
   Markdown headings. `_is_placeholder()` only looked for the template marker,
   and interview-generated files never carry it -- so content-free scaffolding
   counted as a FILLED profile. Two consequences:
     - /status flipped configured:false -> true on no information at all
     - /compiled-context dropped its "The user has not set up their profile
       yet. Do not invent details about them" guard and injected the empty
       headings instead, which is exactly the blank-context-invites-invention
       case that guard exists to prevent.
2. POST /projects/{id}/save returned "updated successfully" when the request
   named no known section, so a typo'd field or a wrong-shaped payload was
   indistinguishable from a real save.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.routers import hierarchy as h


# ── 1. content detection ──────────────────────────────────────────────────────
def test_blank_interview_scaffold_is_not_substance():
    """The exact output of a whitespace-answered interview."""
    text = '# About Me\n- **Name / Role:**    \n- **Background & Mission:**\n   \n'
    assert h._has_substance(text) is False
    assert h._is_placeholder(text) is True


def test_real_answer_is_substance():
    text = '# About Me\n- **Name / Role:** Josh, founder\n'
    assert h._has_substance(text) is True
    assert h._is_placeholder(text) is False


def test_unedited_template_is_a_placeholder():
    text = '# About Me\n- **Name:** _(your name)_\n- **Role:** _(what you do)_\n'
    assert h._is_placeholder(text) is True


def test_heading_only_file_is_a_placeholder():
    assert h._is_placeholder('# About My Voice\n') is True


def test_blockquote_guidance_only_is_a_placeholder():
    assert h._is_placeholder('# X\n> Not filled in yet.\n') is True


def test_plain_prose_counts_as_substance():
    assert h._has_substance('I run a small consultancy for fintech teams.\n') is True


def test_bold_label_with_a_value_counts():
    assert h._has_substance('# Offers\n- **Pro:** $49/mo\n') is True


def test_explicit_marker_still_wins():
    """A file carrying the marker is a placeholder even with prose after it."""
    text = f'# About Me\n{h.PLACEHOLDER_MARKER}\nSome words here.\n'
    assert h._is_placeholder(text) is True


def test_empty_and_none_are_placeholders():
    assert h._is_placeholder('') is True
    assert h._is_placeholder(None) is True


# ── 2. the interview must refuse empty answers ────────────────────────────────
def _answers(**over):
    base = {
        'name_and_role': 'Josh, founder',
        'business_and_icp': 'Strick Tech, sells to devs',
        'voice_and_words': 'Direct, no fluff',
        'offers_and_pricing': 'Pro at $49/mo',
    }
    base.update(over)
    return h.InterviewAnswerRequest(**base)


@pytest.mark.parametrize('field', [
    'name_and_role', 'business_and_icp', 'voice_and_words', 'offers_and_pricing',
])
def test_interview_rejects_a_whitespace_answer(field, tmp_path, monkeypatch):
    monkeypatch.setattr(h, 'TIER1_DIR', tmp_path)
    with pytest.raises(HTTPException) as ex:
        h.interview_generate_tier1(_answers(**{field: '   '}))
    assert ex.value.status_code == 422
    assert field in str(ex.value.detail)


def test_interview_names_every_blank_field(tmp_path, monkeypatch):
    monkeypatch.setattr(h, 'TIER1_DIR', tmp_path)
    with pytest.raises(HTTPException) as ex:
        h.interview_generate_tier1(_answers(
            name_and_role='', business_and_icp='  ',
            voice_and_words='', offers_and_pricing=' ',
        ))
    detail = str(ex.value.detail)
    for f in ('name_and_role', 'business_and_icp', 'voice_and_words', 'offers_and_pricing'):
        assert f in detail


def test_interview_writes_nothing_when_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(h, 'TIER1_DIR', tmp_path)
    with pytest.raises(HTTPException):
        h.interview_generate_tier1(_answers(name_and_role=' '))
    assert not list(tmp_path.glob('*.md'))


def test_interview_accepts_real_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(h, 'TIER1_DIR', tmp_path)
    out = h.interview_generate_tier1(_answers())
    assert out['ok'] is True
    body = (tmp_path / 'about_me.md').read_text()
    assert 'Josh, founder' in body
    assert h._is_placeholder(body) is False


# ── the guard that protects every agent ───────────────────────────────────────
def test_compiled_context_guards_an_empty_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(h, 'TIER1_DIR', tmp_path)
    monkeypatch.setattr(h, '_ensure_tier1_init', lambda: None)
    for key in ('about_me', 'about_my_business', 'about_my_voice', 'about_my_offers'):
        (tmp_path / f'{key}.md').write_text('# Heading\n- **Label:**\n')
    out = h.get_compiled_context(None)
    assert 'Do not invent details' in out['compiled_context']
    assert out['tier1_filled'] == []
    assert len(out['tier1_unfilled']) == 4


def test_compiled_context_uses_real_content(tmp_path, monkeypatch):
    monkeypatch.setattr(h, 'TIER1_DIR', tmp_path)
    monkeypatch.setattr(h, '_ensure_tier1_init', lambda: None)
    (tmp_path / 'about_me.md').write_text('# About Me\n- **Name:** Josh\n')
    for key in ('about_my_business', 'about_my_voice', 'about_my_offers'):
        (tmp_path / f'{key}.md').write_text('# Heading\n')
    out = h.get_compiled_context(None)
    assert 'Do not invent details' not in out['compiled_context']
    assert out['tier1_filled'] == ['about_me']
    assert 'Josh' in out['compiled_context']


# ── 3. a save that writes nothing must not report success ─────────────────────
def test_save_with_no_sections_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(h, '_require_project', lambda pid: tmp_path)
    with pytest.raises(HTTPException) as ex:
        h.save_project('m12', h.ProjectSaveRequest())
    assert ex.value.status_code == 422
    assert 'nothing was saved' in str(ex.value.detail)


def test_save_reports_which_sections_were_written(tmp_path, monkeypatch):
    monkeypatch.setattr(h, '_require_project', lambda pid: tmp_path)
    out = h.save_project('m12', h.ProjectSaveRequest(instructions='# Real', notes='n'))
    assert out['ok'] is True
    assert sorted(out['sections_saved']) == ['instructions', 'notes']
    assert (tmp_path / 'instructions' / 'instructions.md').read_text() == '# Real'


def test_save_allows_deliberately_clearing_a_section(tmp_path, monkeypatch):
    """An empty string is a real edit; only *absent* fields are the no-op."""
    monkeypatch.setattr(h, '_require_project', lambda pid: tmp_path)
    out = h.save_project('m12', h.ProjectSaveRequest(voice=''))
    assert out['sections_saved'] == ['voice']
    assert (tmp_path / 'voice' / 'voice.md').read_text() == ''
