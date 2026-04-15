import re

with open("templates/index.html", "r") as f:
    content = f.read()

# Make sure all features (files, text, reader, browse, latex, html, chat) are present
required_keys = ['active_page == \'files\'', 'active_page == \'text\'', 'active_page == \'reader\'', 'active_page == \'browse\'', 'active_page == \'latex\'', 'active_page == \'html\'', 'active_page == \'chat\'']
for k in required_keys:
    if k not in content:
        print(f"ERROR: {k} missing in templates/index.html")
