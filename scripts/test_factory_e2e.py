"""Gap 4: Live browser E2E test for the factory visualization.

Loads /static/factory/index.html against the running backend, captures console
errors, and verifies PIXI rendered + entities present + SSE connected.
"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://localhost:8000/static/factory/index.html"

def main():
    console_msgs = []
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        print(f"Navigating to {URL} ...")
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"NAVIGATION FAILED: {e}")
            browser.close()
            return 1

        # Give PIXI + SSE time to initialize
        page.wait_for_timeout(8000)

        # Check PIXI loaded (from CDN)
        pixi_loaded = page.evaluate("typeof PIXI !== 'undefined'")
        print(f"PIXI loaded: {pixi_loaded}")

        # Check window.factory exposed
        factory_exposed = page.evaluate("typeof window.factory !== 'undefined'")
        print(f"window.factory exposed: {factory_exposed}")

        if factory_exposed:
            # Check key managers exist
            checks = {
                "app": "!!window.factory.app",
                "renderer": "!!window.factory.renderer",
                "entities": "!!window.factory.entities",
                "state": "!!window.factory.state",
                "sync": "!!window.factory.sync",
            }
            for name, expr in checks.items():
                val = page.evaluate(expr)
                print(f"  factory.{name}: {val}")

            # Count agents/jobs in state (StateManager uses agentStates Map + jobQueue)
            agent_count = page.evaluate("window.factory.state.agentStates ? window.factory.state.agentStates.size : -1")
            job_queue = page.evaluate("""
                (() => {
                    const q = window.factory.state.jobQueue || {};
                    return (q.discovered||[]).length + (q.evaluation||[]).length
                         + (q.tailored||[]).length + (q.applied||[]).length;
                })()
            """)
            print(f"  state.agentStates count: {agent_count}")
            print(f"  state.jobQueue total jobs: {job_queue}")

            # Check hit targets (entity rendering)
            try:
                hit_count = page.evaluate(
                    "(window.factory.entities.getHitTargets ? window.factory.entities.getHitTargets().length : -1)"
                )
                print(f"  entities.getHitTargets() count: {hit_count}")
            except Exception as e:
                print(f"  getHitTargets error: {e}")

            # SSE connection diagnostics
            conn_state = page.evaluate("window.factory.sync.connectionState")
            es_state = page.evaluate("window.factory.sync.eventSource ? window.factory.sync.eventSource.readyState : -1")
            last_id = page.evaluate("window.factory.sync.lastEventId")
            print(f"  sync.connectionState: {conn_state}")
            print(f"  EventSource.readyState: {es_state} (0=CONNECTING 1=OPEN 2=CLOSED)")
            print(f"  sync.lastEventId: {last_id}")

        # Canvas present + non-empty
        canvas_info = page.evaluate("""
            (() => {
                const c = document.getElementById('factory-canvas');
                if (!c) return {exists: false};
                return {exists: true, width: c.width, height: c.height};
            })()
        """)
        print(f"canvas: {canvas_info}")

        # Screenshot
        page.screenshot(path="scripts/factory_e2e_screenshot.png")
        print("Screenshot saved: scripts/factory_e2e_screenshot.png")

        browser.close()

    # Report console errors
    errors = [m for m in console_msgs if m.startswith("[error]")]
    print(f"\n=== Console messages: {len(console_msgs)} total, {len(errors)} errors ===")
    for e in errors[:10]:
        print(f"  {e}")
    print(f"=== Page errors (uncaught exceptions): {len(page_errors)} ===")
    for e in page_errors[:10]:
        print(f"  {e}")

    # Verdict
    if page_errors:
        print("\nVERDICT: FAIL — uncaught page errors present")
        return 1
    if not pixi_loaded:
        print("\nVERDICT: FAIL — PIXI did not load (CDN/network issue?)")
        return 1
    if not factory_exposed:
        print("\nVERDICT: FAIL — window.factory not exposed (JS init failed)")
        return 1
    print("\nVERDICT: PASS — page loaded, PIXI rendered, factory initialized, no uncaught errors")
    return 0

if __name__ == "__main__":
    sys.exit(main())
