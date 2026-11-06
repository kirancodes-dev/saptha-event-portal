"""
tests/test_chatbot_campus_facts.py — UPG-108: until the owner confirms the
campus facts, the chatbot doesn't state them. Campus questions are answered
"Please check with the college office.", and the AI's prompt carries no campus
facts, only how the portal itself works.
"""
import pytest

CHECK = "Please check with the college office."
UNCONFIRMED = ('North Gate', 'Basketball', 'Zone A', 'Administration Block', 'Food Court', 'help@sapthagiri.edu',
               'student ID card', 'Library Block', 'Sports Arena')


@pytest.mark.parametrize('question', ['Is parking available on campus?', 'Where is the canteen?',
                                      'Where is the Seminar Hall?', 'How do I get to Zone B?', 'Is there wifi?'])
def test_campus_questions_get_the_college_office(real_app, question):
    flask_app, _ = real_app
    reply = flask_app.test_client().post('/chatbot/ask', json={'message': question}).get_json()['reply']
    assert reply == CHECK


def test_the_ai_prompt_carries_no_campus_facts(real_app, monkeypatch):
    import zoho_zia
    flask_app, _ = real_app
    prompts = []
    monkeypatch.setattr(zoho_zia, 'ask_zia_chatbot', lambda message, prompt: prompts.append(prompt) or 'ok')
    reply = flask_app.test_client().post('/chatbot/ask', json={'message': 'Which events are open?'}).get_json()['reply']
    assert reply == 'ok'
    [prompt] = prompts
    for fact in UNCONFIRMED:
        assert fact not in prompt, fact
    assert CHECK in prompt and 'PORTAL FAQ' in prompt
