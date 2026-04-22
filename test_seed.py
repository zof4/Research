from playwright.sync_api import sync_playwright

def run_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://127.0.0.1:8003/")

        # Login
        if page.locator("input[placeholder='Username']").is_visible():
            page.get_by_placeholder("Username").fill("admin")
            page.get_by_placeholder("Password").fill("dropper")
            page.locator("button:has-text('Sign in')").click()
            page.wait_for_timeout(1000)

        # Open HTML viewer
        page.goto("http://127.0.0.1:8003/html/ipad-viewer?owner=admin")
        page.wait_for_timeout(2000)

        # Check source code
        source_code = page.locator(".CodeMirror-code").inner_text()
        print("Initial Source length:", len(source_code))

        # Simulate a drag on a node inside the iframe
        frame = page.frame_locator("#preview-frame")

        # Get position of a node
        node = frame.locator(".node").first
        box = node.bounding_box()
        print("Initial node position:", box)

        # Drag the node
        node.hover()
        page.mouse.down()
        page.mouse.move(box['x'] + 100, box['y'] + 100)
        page.mouse.up()

        page.wait_for_timeout(2000)

        new_source_code = page.locator(".CodeMirror-code").inner_text()
        print("New Source length:", len(new_source_code))
        if "org-chart-state" in new_source_code:
            print("Found org-chart-state in new source!")
        else:
            print("Did NOT find org-chart-state in new source!")

        browser.close()

run_test()
