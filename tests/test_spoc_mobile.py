"""
tests/test_spoc_mobile.py — UPG-106: the SPOC event panel can't be wider
than a phone screen, and its header stacks so buttons can't squeeze the title.
"""


def test_the_spoc_event_panel_fits_a_phone():
    with open('templates/spoc/dashboard.html', encoding='utf-8') as fh:
        html = fh.read()
    assert 'grid-template-columns: minmax(0, 1fr);' in html     # a plain 1fr grew to its content
    assert '.event-head { flex-direction: column;' in html      # header stacks on phones
    assert 'class="event-head d-flex' in html and 'class="event-head-actions d-flex' in html
