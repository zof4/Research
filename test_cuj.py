from playwright.sync_api import sync_playwright

def run_cuj(page):
    page.goto("http://127.0.0.1:8003/")
    # If the login form is visible, login
    if page.locator("input[placeholder='Enter your username']").is_visible() or page.locator("input[name='username']").is_visible():
        page.locator("input[name='username']").fill("admin")
        page.locator("input[name='password']").fill("dropper")
        try:
            page.locator("button:has-text('Sign in')").click()
        except:
            pass
        page.wait_for_timeout(2000)

    page.goto("http://127.0.0.1:8003/")
    page.wait_for_timeout(2000)
    page.screenshot(path="screenshot_dashboard.png")

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
