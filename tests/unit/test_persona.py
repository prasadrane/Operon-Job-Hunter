from src.core import persona


def test_persona_constants_are_fictional():
    assert persona.SAMPLE_FULL_NAME == 'Alex Rivera'
    assert persona.SAMPLE_EMAIL.endswith('@example.com')
    assert '555' in persona.SAMPLE_PHONE
    assert persona.SAMPLE_RESUME_PDF_NAME == 'Alex_Rivera_Resume.pdf'
    assert 'Python' in persona.SAMPLE_SKILLS


def test_persona_summary_mentions_no_real_entities():
    text = persona.SAMPLE_PROFILE_SUMMARY + persona.SAMPLE_FULL_NAME
    assert "Prasad" not in text and "Rane" not in text
