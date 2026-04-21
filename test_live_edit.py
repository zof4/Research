from playwright.sync_api import sync_playwright

def run(page):
    page.goto("http://127.0.0.1:8003/")
    # Login
    if page.locator("input[placeholder='Username']").is_visible():
        page.get_by_placeholder("Username").fill("admin")
        page.get_by_placeholder("Password").fill("dropper")
        try:
            page.get_by_role("button", name="Sign in").click()
        except:
            page.locator("button:has-text('Sign in')").click()
        page.wait_for_timeout(1000)

    # Let's get the first item from the dashboard
    page.goto("http://127.0.0.1:8003/html")
    page.wait_for_timeout(2000)

    # Click the first HTML item to open it
    page.locator(".file-item").first.click()
    page.wait_for_timeout(2000)

    # Let's verify what is rendered inside the iframe
    frame = page.frame_locator("#preview-frame")
    print("Inner HTML:")
    print(frame.locator("body").inner_html()[:500])

    # Let's drag a node in the iframe

    # Wait for node to be visible
    node = frame.locator(".node").first
    node.wait_for()

    box = node.bounding_box()
    print("Node box:", box)

    # Drag it
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 100, box["y"] + box["height"] / 2 + 100)
    page.mouse.up()

    page.wait_for_timeout(3000)
    print("Done waiting.")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    run(page)
    browser.close()
