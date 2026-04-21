from playwright.sync_api import sync_playwright
import os

def run_cuj(page):
    page.goto("http://127.0.0.1:8003/")
    if page.locator("input[name='username']").is_visible() or page.locator("input[placeholder='Username']").is_visible():
        try:
             page.locator("input[name='username']").fill("admin")
             page.locator("input[name='password']").fill("dropper")
        except:
             page.get_by_placeholder("Username").fill("admin")
             page.get_by_placeholder("Password").fill("dropper")
        try:
            page.get_by_role("button", name="Log in").click()
        except:
            page.locator("button:has-text('Sign in')").click()
        page.wait_for_timeout(1000)

    page.goto("http://127.0.0.1:8003/html/ipad-viewer")
    page.wait_for_timeout(2000)

    # Click + New
    try:
        page.locator("#btn-new-file").click()
    except Exception as e:
        print(f"Failed to click btn-new-file: {e}")

    page.wait_for_timeout(1000)

    frame = page.frame_locator("#preview-frame")
    try:
        frame.locator("body").click()
        page.keyboard.type(" Live edited text!")
    except Exception as e:
        print(f"Failed to edit iframe: {e}")

    page.wait_for_timeout(2000)

    os.makedirs("/home/jules/verification/screenshots", exist_ok=True)
    page.screenshot(path="/home/jules/verification/screenshots/verification.png")
    page.wait_for_timeout(1000)

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        os.makedirs("/home/jules/verification/videos", exist_ok=True)
        context = browser.new_context(
            record_video_dir="/home/jules/verification/videos"
        )
        page = context.new_page()
        try:
            run_cuj(page)
        finally:
            context.close()
            browser.close()
