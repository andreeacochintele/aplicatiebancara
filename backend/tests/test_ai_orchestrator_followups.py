from app.ai.orchestrator import followups


# ---- vague/duplicate suggestion fix: each chip must map to one specific
# missing thing and never repeat a question the agent's own reply already
# asked (e.g. Credit's "how much extra would you like to simulate?").


def test_system_prompt_forbids_vague_generic_suggestions():
    lowered = followups._SYSTEM_PROMPT.lower()
    assert "short, unambiguous" in lowered
    assert "vague or generic" in lowered


def test_system_prompt_forbids_repeating_the_assistants_own_question():
    lowered = followups._SYSTEM_PROMPT.lower()
    assert "do not create a chip that repeats or closely rephrases" in lowered


# ---- wrong-speaker fix: a chip's text is sent verbatim as the USER's own
# outgoing message when tapped, so it must read as something the user would
# say — never a question mirrored back from the agent's own reply (e.g. the
# agent asks "care vrei: soldul actual, ultimele 10 tranzacții sau detaliile
# cardului?" and a chip must not just repeat that question).


def test_system_prompt_forbids_chips_phrased_as_questions_to_the_user():
    lowered = followups._SYSTEM_PROMPT.lower()
    assert "never phrase a chip as a question directed at the user" in lowered
    assert "never phrase a chip as a question mirrored or restated from" in lowered


def test_system_prompt_requires_chips_to_read_as_the_users_own_message():
    lowered = followups._SYSTEM_PROMPT.lower()
    assert "a first-person statement, request, or answer" in lowered


def test_system_prompt_instructs_splitting_a_multiple_choice_question_into_one_chip_per_option():
    lowered = followups._SYSTEM_PROMPT.lower()
    assert "generate one chip per option" in lowered
    assert "never one chip that" in lowered and "repeats the assistant's question back" in lowered
