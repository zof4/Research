from playwright.sync_api import sync_playwright
import time

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("console", lambda msg: print(f"Browser console: {msg.text}"))

    page.goto("http://localhost:8003/")
    page.evaluate('''() => {
        document.querySelector('input[name="username"]').value = 'admin';
        document.querySelector('input[name="password"]').value = 'dropper';
        const form = document.querySelector('form');
        form.removeAttribute('data-async');
        form.submit();
    }''')

    page.wait_for_load_state('networkidle')
    page.goto("http://localhost:8003/")
    page.wait_for_load_state('networkidle')

    time.sleep(1)
    page.screenshot(path="debug_after_login.png")

    html = page.content()
    with open('vue_post_login.html', 'w') as f:
        f.write(html)

    print("Does the app actually load? '#app' in HTML:", 'id="app"' in html)

    browser.close()

with sync_playwright() as playwright:
    run(playwright)
