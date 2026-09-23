"""Local browser fixtures only; never connect to a business browser or server."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from playwright.sync_api import sync_playwright, TimeoutError

sys.path.insert(0, str(Path(__file__).parents[1]))
from src.approver import ApprovalHelper
from src.browser import BrowserHelper


class ApprovalWaitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel="msedge", headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.helper = ApprovalHelper(BrowserHelper(), {"approval": {
            "dept_select_text": "Risk", "final_confirm_button_selector": "#final",
        }}, log_callback=Mock())

    def fixture(self, delay):
        self.page.set_content(f"""<iframe></iframe><script>
        window.events=[];
        setTimeout(() => {{
          const doc=document.querySelector('iframe').contentDocument;
          doc.body.innerHTML='<button id="dept">Risk</button><button id="final" disabled>OK</button>';
          doc.querySelector('#dept').onclick=()=>{{
            events.push('department');
            setTimeout(()=>doc.querySelector('#final').disabled=false, 250);
          }};
          doc.querySelector('#final').onclick=()=>events.push('final');
        }}, {delay});</script>""")
        self.helper.main_page = self.page
        return self.page.frames[1]

    def test_ready_and_delayed_iframe_preserve_order(self):
        for delay in (0, 1400):
            with self.subTest(delay=delay):
                frame = self.fixture(delay)
                start = time.monotonic()
                self.helper._handle_subsequent_pages(frame)
                elapsed = time.monotonic() - start
                self.assertEqual(self.page.evaluate("events"), ["department", "final"])
                self.assertLess(elapsed, delay / 1000 + 2)
                print(f"Local popup delay={delay}ms, flow={elapsed:.2f}s")

    def test_click_waits_for_creation_and_ignores_hidden_duplicate(self):
        self.page.set_content("""<button class='ok' hidden>old</button><script>
        window.clicked=0;setTimeout(()=>{
          let b=document.createElement('button'); b.className='ok'; b.textContent='new';
          b.onclick=()=>clicked++; document.body.append(b);
        },300);</script>""")
        BrowserHelper().safe_click(self.page, ".ok", timeout=1500)
        self.assertEqual(self.page.evaluate("clicked"), 1)

    def test_missing_department_never_clicks_final(self):
        self.page.set_content('<button id="final" onclick="window.clicked=true">OK</button>')
        with self.assertRaises(RuntimeError):
            self.helper._wait_click([(self.page, "page")], lambda p: p.get_by_text("Risk", exact=True), "department", timeout=250)
        self.assertIsNone(self.page.evaluate("window.clicked"))

    def test_overlay_and_ambiguous_targets_are_not_forced(self):
        for html in (
            '<button id="final">OK</button><div style="position:fixed;inset:0;z-index:99"></div>',
            '<button id="final">OK</button><button id="final">OK</button>',
        ):
            self.page.set_content(html)
            self.page.evaluate("window.clicks=0; document.querySelectorAll('button').forEach(b=>b.onclick=()=>clicks++)")
            with self.assertRaises(RuntimeError):
                self.helper._wait_click([(self.page, "page")], lambda p: p.locator("#final"), "final", timeout=300)
            self.assertEqual(self.page.evaluate("clicks"), 0)

    def test_safe_click_missing_target_respects_timeout(self):
        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            BrowserHelper().safe_click(self.page, "#missing", timeout=250)
        self.assertLess(time.monotonic() - start, 1.5)

    def test_full_detail_waits_for_each_new_window(self):
        self.helper.approval_cfg.update(approve_button_selector="#approve", confirm_button_selector="#confirm")
        self.helper.browser.find_contract_frame = Mock(return_value=None)
        self.page.set_content('''<button id="approve">Approve</button><script>
        window.events=[];
        approve.onclick=()=>{events.push('approve');setTimeout(()=>{
          let b=document.createElement('button');b.id='confirm';b.textContent='Confirm';
          b.onclick=()=>{events.push('confirm');b.remove();setTimeout(()=>{
            document.body.insertAdjacentHTML('beforeend','<button id="dept">Risk</button><button id="final" disabled>Final</button>');
            dept.onclick=()=>{events.push('department');setTimeout(()=>final.disabled=false,200)};
            final.onclick=()=>events.push('final');
          },300)};document.body.append(b);
        },300)};</script>''')
        start = time.monotonic()
        self.helper._process_detail(self.page)
        elapsed = time.monotonic() - start
        self.assertEqual(self.page.evaluate("events"), ["approve", "confirm", "department", "final"])
        self.assertLess(elapsed, 3)
        print(f"Local complete click flow={elapsed:.2f}s")

    def test_test_mode_cancels_without_confirming(self):
        self.page.set_content('''<button>Risk</button><button id="final" onclick="window.confirmed=true">OK</button>
        <button id="buttonCancel" onclick="window.cancelled=true">Cancel</button>''')
        self.helper.test_mode = True
        self.helper._handle_subsequent_pages(self.page)
        self.assertTrue(self.page.evaluate("window.cancelled"))
        self.assertIsNone(self.page.evaluate("window.confirmed"))


if __name__ == "__main__":
    unittest.main()
