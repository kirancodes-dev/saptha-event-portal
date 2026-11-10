"""
tests/test_wizard_form.py — UPG-219 on the real database layer: the
registration form is what step 6 of the event wizard shows. Name and email are
fixed; every other question is the SPOC's, in the SPOC's order, phone and USN
included; the event type's catalogue questions are only suggested; "Checkboxes"
shows its choices; the members' USN and phone are chosen in step 6; editing
lists the form and leaves it alone. A request without step 6's list (the API,
older scripts) keeps the catalogue form.
"""
import json
import re

from tests.test_event_creation import _create, _event_id, _form, _get, spoc  # noqa: F401  (fixture)
from tests.test_form_builder_choices import _control, _required
from tests.test_form_builder_order import _names_in_order, _section
from tests.test_integration_flow import _unique

USN = {'id': 'usn', 'type': 'text', 'label': 'USN / Roll Number', 'required': False, 'options': []}
SHIRT = {'id': 'q_shirt', 'type': 'select', 'label': 'T-shirt size', 'required': True, 'options': ['S', 'M', 'L']}
IDEA = {'id': 'q_idea', 'type': 'textarea', 'label': 'Your idea', 'required': False, 'options': []}
SKILLS = {'id': 'q_skills', 'type': 'checkbox_group', 'label': 'Skills', 'required': False,
          'options': ['Web', 'ML', 'IoT']}
HACKATHON_TEMPLATE = ('github_url', 'tech_stack', 'project_pitch', 'tshirt_size', 'dietary_preference')


def _step6(questions, **extra):
    """What step 6 sends: its list of questions (name and email are added by the server)."""
    return dict({'form_step6': '1', 'form_step6_json': json.dumps(questions)}, **extra)


def _open(spoc, data):  # noqa: F811
    """Create the event in the wizard, publish it, and return (event_id, its registration page)."""
    event_id = _event_id(_create(spoc['client'], data))
    assert spoc['client'].post(f'/spoc/event/{event_id}/publish').status_code in (200, 302)
    page = spoc['app'].test_client().get(f'/forms/register/{event_id}').get_data(as_text=True)
    return event_id, page


def _builder_fields(spoc, event_id):  # noqa: F811
    builder = spoc['client'].get(f'/forms/builder/{event_id}').get_data(as_text=True)
    return json.loads(re.search(r'const existingForm = (.*);\n', builder).group(1))['fields']


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_page_asks_exactly_step_6s_questions_in_its_order(spoc):  # noqa: F811
    # Phone removed, USN kept optional, then two of the SPOC's questions
    event_id, page = _open(spoc, _form('custom', _unique('Step Six'), **_step6([USN, SHIRT, IDEA])))
    assert _names_in_order(page) == ['full_name', 'email', 'usn', 'q_shirt', 'q_idea']
    assert _control(page, 'phone') is None
    assert _required(page, 'full_name') and _required(page, 'email') and _required(page, 'q_shirt')
    assert not _required(page, 'usn') and not _required(page, 'q_idea')
    # The builder opens with the same list, as the SPOC's own form
    assert [f['id'] for f in _builder_fields(spoc, event_id)] == ['full_name', 'email', 'usn', 'q_shirt', 'q_idea']
    assert _get(spoc['db'], event_id)['form_chosen'] is True


def test_phone_moved_below_a_question_stays_there(spoc):  # noqa: F811
    phone = {'id': 'phone', 'type': 'tel', 'label': 'Phone Number', 'required': True, 'options': []}
    _, page = _open(spoc, _form('custom', _unique('Phone Later'), **_step6([SHIRT, phone])))
    assert _names_in_order(page) == ['full_name', 'email', 'q_shirt', 'phone']
    assert 'name="phone"' not in _section(page, 'Participant details')


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_a_hackathon_gets_none_of_the_template_questions_unless_added(spoc):  # noqa: F811
    wizard = spoc['client'].get('/spoc/create_event?type=hackathon').get_data(as_text=True)
    suggested = json.loads(re.search(r'<script type="application/json" id="wz-suggest">(.*?)</script>',
                                     wizard, re.S).group(1))
    offered = {q['id']: q for q in suggested['hackathon']}
    assert set(HACKATHON_TEMPLATE) <= set(offered)            # offered in step 6 ...

    _, page = _open(spoc, _form('hackathon', _unique('Plain Hack'), **_step6([USN])))
    for fid in HACKATHON_TEMPLATE:                              # ... never added unseen
        assert _control(page, fid) is None, fid
    assert _names_in_order(page) == ['full_name', 'email', 'usn', 'team_name']

    # One added from the suggestions is asked, with its choices
    _, page = _open(spoc, _form('hackathon', _unique('Shirt Hack'), **_step6([USN, offered['tshirt_size']])))
    assert _required(page, 'tshirt_size')
    assert all(_control(page, fid) is None for fid in HACKATHON_TEMPLATE if fid != 'tshirt_size')


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_checkboxes_show_each_choice_and_a_choice_without_choices_is_refused(spoc):  # noqa: F811
    _, page = _open(spoc, _form('custom', _unique('Skills Fair'), **_step6([SKILLS])))
    for option in ('Web', 'ML', 'IoT'):
        assert re.search(rf'<input type="checkbox" name="q_skills" value="{option}"', page), option

    title = _unique('No Choices')
    empty = dict(SHIRT, options=[])
    resp = _create(spoc['client'], _form('custom', title, **_step6([empty])))
    assert resp.status_code == 400
    assert "needs at least one option" in resp.get_data(as_text=True)
    assert not [d for d in spoc['db'].collection('events').where('title', '==', title).stream()]


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_members_usn_and_phone_are_chosen_in_step_6(spoc):  # noqa: F811
    wizard = spoc['client'].get('/spoc/create_event').get_data(as_text=True)
    assert 'Also ask for' not in wizard and 'req_member_usn' not in wizard
    assert 'name="member_usn"' in wizard and 'name="member_phone"' in wizard

    event_id, page = _open(spoc, _form('hackathon', _unique('Member Hack'), team_min='2', team_max='3',
                                       **_step6([USN], member_usn='required', member_phone='optional')))
    # Member 2 is needed (team of at least 2): USN required, phone optional; member 3 is extra
    assert _required(page, 'member_1_usn') and not _required(page, 'member_1_phone')
    assert _control(page, 'member_1_phone') is not None
    assert not _required(page, 'member_2_usn')
    assert _get(spoc['db'], event_id)['form_member_fields'] == {'usn': 'required', 'phone': 'optional'}

    # "Don't ask" leaves them out
    _, page = _open(spoc, _form('hackathon', _unique('Lean Hack'), team_min='2', team_max='3',
                                **_step6([USN], member_usn='off', member_phone='off')))
    assert _control(page, 'member_1_usn') is None and _control(page, 'member_1_phone') is None
    assert _required(page, 'member_1_email')


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_editing_lists_the_form_and_leaves_it_alone(spoc):  # noqa: F811
    title = _unique('Edit Me')
    event_id, _ = _open(spoc, _form('custom', title, **_step6([USN, SHIRT, IDEA])))
    stored = spoc['db'].collection('event_forms').document(event_id).get().to_dict()

    setup = spoc['client'].get(f'/spoc/event/{event_id}/setup').get_data(as_text=True)
    outline = re.search(r'<ol class="mb-2" id="form-outline">(.*?)</ol>', setup, re.S).group(1)
    labels = [re.sub(r'<.*', '', li).strip() for li in re.findall(r'<li>(.*?)</li>', outline, re.S)]
    assert labels == ['Full Name', 'Email Address', 'USN / Roll Number', 'T-shirt size', 'Your idea']
    assert 'Also ask for' not in setup and 'id="field-rows"' not in setup

    # Saving the edit (even with a stray step-6 list) doesn't touch the form
    resp = spoc['client'].post(f'/spoc/event/{event_id}/setup',
                               data=_form('custom', title + ' (moved)', venue='Hall 9', **_step6([IDEA])))
    assert resp.status_code == 302
    assert spoc['db'].collection('event_forms').document(event_id).get().to_dict() == stored
    assert _get(spoc['db'], event_id)['form_chosen'] is True


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_a_request_without_step_6s_list_keeps_the_template_form(spoc):  # noqa: F811
    event_id = _event_id(_create(spoc['client'], _form('hackathon', _unique('Scripted Hack'))))
    ids = [f.get('id') for f in spoc['db'].collection('event_forms').document(event_id).get().to_dict()['fields']]
    assert 'github_url' in ids and 'phone' in ids
    assert not _get(spoc['db'], event_id).get('form_chosen')
