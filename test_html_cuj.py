from playwright.sync_api import sync_playwright

def run_cuj(page):
    page.goto("http://127.0.0.1:8003/")
    # Fill login form if input is visible
    if page.locator("input[placeholder='Username']").is_visible():
        page.get_by_placeholder("Username").fill("admin")
        page.get_by_placeholder("Password").fill("dropper")
        try:
            page.get_by_role("button", name="Sign in").click()
        except:
            page.locator("button:has-text('Sign in')").click()
        page.wait_for_timeout(1000)

    page.goto("http://127.0.0.1:8003/html/ipad-viewer?owner=admin")
    page.wait_for_timeout(2000)
    page.screenshot(path="screenshot_ipad_viewer.png")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("console", lambda msg: print(f"Browser console: {msg.text}"))
    page.on("pageerror", lambda exc: print(f"Browser error: {exc}"))
    try:
        run_cuj(page)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.close()
