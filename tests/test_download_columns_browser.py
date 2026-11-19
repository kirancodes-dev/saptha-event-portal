"""
tests/test_download_columns_browser.py — UPG-325 in a real browser (headless
Chromium against the app on a local server): a download button opens the
"Choose the columns" box with every column ticked; Select none leaves only
the columns that must stay; the file has only the ticked columns; Select
all downloads the whole file.
"""
import csv
import io

from tests.test_hackathon_marks import mk  # noqa: F401
from tests.test_hackathon_phase2 import p2  # noqa: F401
from tests.test_hackathon_portal import hack  # noqa: F401
from tests.test_phone_journey import _login_in_browser, _routes


def _header(download):
    with open(download.path(), encoding='utf-8') as f:
        return next(csv.reader(io.StringIO(f.read())))


def test_the_column_box_downloads_only_the_ticked_columns(mk):  # noqa: F811
    from tests.headless import chromium, live_server
    eid, _ = mk['mk_setup'](submit=('Alpha', 'Bravo'))
    mk['after']()
    errors = []
    p, browser = chromium()
    try:
        with live_server(mk['app']) as server:
            base = server.url
            ctx = browser.new_context(viewport={'width': 1280, 'height': 900}, accept_downloads=True)
            _routes(ctx, base)
            page = ctx.new_page()
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            _login_in_browser(page, base, mk['spoc'], 'ClubSPOC')
            page.goto(f'{base}/spoc/hackathon/{eid}#evaluation')

            link = 'a[data-pick-columns][href$="/evaluators.csv"]'
            page.click(link)
            page.wait_for_selector('#pickColumnsBox')
            boxes = page.locator('#pickColumnsBox input[type=checkbox]')
            total = boxes.count()
            assert total >= 8
            assert page.locator('#pickColumnsBox input[type=checkbox]:checked').count() == total   # all ticked
            assert page.locator('#pickColumnsBox input[type=checkbox]:disabled').count() == 2      # code and score
            assert 'Always included: Team code, Score (out of 100).' in page.inner_text('#pickColumnsBox')

            page.click('#pickColumnsBox [data-pick-none]')
            assert page.locator('#pickColumnsBox input[type=checkbox]:checked').count() == 2
            page.check('#pickColumnsBox label:has-text("Lead email") input')
            with page.expect_download() as got:
                page.click('#pickColumnsBox button:has-text("Download")')
            assert _header(got.value) == ['Team code', 'Score (out of 100)', 'Lead email']
            assert page.locator('#pickColumnsBox').count() == 0

            # Select all: the whole file, as before
            page.click(link)
            page.wait_for_selector('#pickColumnsBox')
            page.click('#pickColumnsBox [data-pick-none]')
            page.click('#pickColumnsBox [data-pick-all]')
            with page.expect_download() as got:
                page.click('#pickColumnsBox button:has-text("Download")')
            assert len(_header(got.value)) == total

            # Cancel closes the box and downloads nothing
            page.click(link)
            page.wait_for_selector('#pickColumnsBox')
            page.click('#pickColumnsBox button:has-text("Cancel")')
            assert page.locator('#pickColumnsBox').count() == 0
    finally:
        browser.close()
        p.stop()
    assert errors == []
