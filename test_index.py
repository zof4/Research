from app import app, build_template_context

with app.test_request_context('/'):
    try:
        from flask import render_template
        render_template("app_index.html", **build_template_context("home"))
    except Exception as e:
        import traceback
        traceback.print_exc()
