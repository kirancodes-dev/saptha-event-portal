#!/usr/bin/env python3
"""
Render `report_viewer.html` in a headless browser and save as PDF.

Usage: python3 reports/generate_pdf_from_md.py

This script starts a temporary HTTP server serving the repo root, launches
pyppeteer to render the local viewer page, and writes `reports/SapthaEvent_Report.pdf`.
"""
import asyncio
import http.server
import socketserver
import threading
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "SapthaEvent_Complete_Website_Workflow_and_Permission_Report.pdf"
PORT = 8002


class SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_server():
    handler = SilentHandler
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


async def render_pdf():
    from pyppeteer import launch

    browser = await launch(args=['--no-sandbox'])
    page = await browser.newPage()
    url = f'http://127.0.0.1:{PORT}/reports/report_viewer.html'
    await page.goto(url, {'waitUntil': 'networkidle2'})
    # A4 dimensions, tighter margins, and header/footer templates
    header_html = '<div style="font-size:10px;width:100%;text-align:center;color:#6b7280;font-family:Inter,Arial;">SapthaEvent Portal — Project Workflow & Approval</div>'
    footer_html = '<div style="font-size:10px;width:100%;text-align:center;color:#6b7280;font-family:Inter,Arial;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>'
    await page.pdf({
        'path': str(OUTPUT),
        'format': 'A4',
        'printBackground': True,
        'displayHeaderFooter': True,
        'headerTemplate': header_html,
        'footerTemplate': footer_html,
        'margin': {'top': '10mm','bottom':'12mm','left':'10mm','right':'10mm'}
    })
    await browser.close()


def main():
    cwd = Path(__file__).resolve().parents[1]
    print(f"Starting temporary HTTP server at http://127.0.0.1:{PORT}/ (serving {cwd})")
    server = start_server()
    try:
        asyncio.get_event_loop().run_until_complete(render_pdf())
        print(f"PDF written to: {OUTPUT}")
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
