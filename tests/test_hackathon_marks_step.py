"""
tests/test_hackathon_marks_step.py — UPG-324: with outside evaluators, step 3
(upload their file) is always on the page, so the SPOC knows where it is.
Before the deadline it is greyed out with the time it opens; after, it works.
"""
import io

import services_hackathon as hk
import services_hackathon_marks as marks
from tests.test_hackathon_marks import CODES, _csv, mk  # noqa: F401
from tests.test_hackathon_phase2 import p2  # noqa: F401
from tests.test_hackathon_portal import _page, hack  # noqa: F401


def _step(page):
    start = page.index('data-marks-step')
    return page[start:page.index('</form>', start)]


# 1. Before the deadline: step 3 is shown, disabled, with when it opens
def test_before_the_deadline_step_3_shows_when_it_opens(mk):  # noqa: F811
    eid, _ = mk['mk_setup'](submit=('Alpha',))
    page = _page(mk['owner'], f'/spoc/hackathon/{eid}')
    assert 'id="marks-upload"' in page and 'href="#marks-upload"' in page   # a button at the top goes to it
    step = _step(page)
    assert "3. Upload the evaluators' file here" in step
    assert 'data-marks-wait' in step and 'Opens when submissions close:' in step
    event = mk['ev'](eid)
    assert hk.show(hk.form(event)['closes_at'], event) in step       # the time, in the event's time zone
    assert 'type="file" id="mkFile"' in step and 'required disabled' in step
    assert '<button class="btn btn-primary" type="submit" disabled>Upload and check</button>' in step
    assert 'href="#deadline"' in step                                 # how to open it earlier

    # The server still refuses an upload before the deadline
    r = mk['upload'](eid, _csv([[CODES['Alpha'], 80]]))
    assert r.status_code == 302
    assert not marks.kept(mk['ev'](eid) | {'id': eid}).get('id')


# 2. After the deadline: the same step works
def test_after_the_deadline_step_3_is_open(mk):  # noqa: F811
    eid, _ = mk['mk_setup'](submit=('Alpha',))
    mk['after']()
    step = _step(_page(mk['owner'], f'/spoc/hackathon/{eid}'))
    assert "3. Upload the evaluators' file here" in step
    assert 'data-marks-wait' not in step and 'disabled' not in step
    r = mk['owner'].post(f'/spoc/hackathon/{eid}/marks/preview',
                         data={'file': (io.BytesIO(_csv([[CODES['Alpha'], 80]]).encode()), 'm.csv'), 'n': '1'},
                         content_type='multipart/form-data')
    assert r.status_code == 200
    assert marks.kept(mk['ev'](eid) | {'id': eid}).get('id')


# 3. Judges or AI scoring: no upload step and no button for it
def test_without_outside_evaluators_there_is_no_upload_step(mk):  # noqa: F811
    eid, _ = mk['mk_setup'](submit=('Alpha',), file_mode=False)
    page = _page(mk['owner'], f'/spoc/hackathon/{eid}')
    assert 'id="marks-upload"' not in page and 'href="#marks-upload"' not in page
