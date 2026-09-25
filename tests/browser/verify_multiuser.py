#!/usr/bin/env -S uv run --quiet --with playwright python
"""Verify account isolation in a disposable Aspire environment."""

import argparse
import json
import os
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright


def request(page, url, method, path, body=None):
    response = page.request.fetch(
        f"{url}/api{path}", method=method,
        headers={"Origin": url, "Content-Type": "application/json"},
        data=json.dumps(body) if body is not None else None,
    )
    return response, response.json() if response.status != 204 else None


def verify(url, artifacts):
    artifacts.mkdir(parents=True, exist_ok=True)
    password = os.environ["PARAMES_ADMIN_PASSWORD"]
    suffix = uuid.uuid4().hex[:12]
    trace = {"url": url, "steps": []}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        admin = browser.new_context(viewport={"width": 1280, "height": 900})
        a = browser.new_context(viewport={"width": 1280, "height": 900})
        b = browser.new_context(viewport={"width": 1280, "height": 900})
        try:
            admin_page = admin.new_page()
            admin_page.goto(url, wait_until="networkidle")
            admin_page.get_by_label("Email").fill("mail@manuelseeger.de")
            admin_page.get_by_label("Password").fill(password)
            admin_page.get_by_role("button", name="Log in").click()
            admin_page.get_by_role("link", name="Dashboard").wait_for()
            admin_page.get_by_role("link", name="Alert definitions").click()
            admin_page.locator("table.table tbody tr").first.wait_for()
            admin_page.screenshot(path=artifacts / "01-admin.png", full_page=True)
            response, definitions = request(admin_page, url, "GET", "/alert-definitions")
            assert response.status == 200 and definitions, "Admin cannot read seeded definitions"
            template = definitions[0]
            trace["steps"].append("Admin logged in and saw the seeded alert definitions.")

            pages = []
            for context, label in ((a, "a"), (b, "b")):
                page = context.new_page()
                page.goto(f"{url}/#/signup", wait_until="networkidle")
                page.get_by_label("Email").fill(f"verify-{suffix}-{label}@example.com")
                page.get_by_label("Password").fill("verification-password-12345")
                page.get_by_role("button", name="Sign up").click()
                page.get_by_role("link", name="Alert definitions").wait_for()
                assert page.get_by_role("link", name="Dashboard").count() == 0
                assert page.get_by_role("link", name="Logs").count() == 0
                assert page.get_by_role("link", name="Detections").count() == 1
                pages.append(page)
            pages[0].screenshot(path=artifacts / "02-regular.png", full_page=True)
            trace["steps"].append("Two users signed up and saw only alert and detection navigation.")

            shared_name = f"verify-{suffix}"
            body = {key: value for key, value in template.items()
                    if key not in ("id", "_id", "owner_id", "created_at", "updated_at")}
            body.update(name=shared_name, delivery=["console"])
            ids = []
            for page in pages:
                response, created = request(page, url, "POST", "/alert-definitions", body)
                assert response.status == 201, f"Create failed: {response.status} {created}"
                ids.append(created["id"])
            assert ids[0] != ids[1]
            for page, own_id, foreign_id in ((pages[0], ids[0], ids[1]), (pages[1], ids[1], ids[0])):
                response, listed = request(page, url, "GET", "/alert-definitions")
                assert response.status == 200 and [item["id"] for item in listed] == [own_id]
                for method, path, payload in (
                    ("GET", f"/alert-definitions/{foreign_id}", None),
                    ("PATCH", f"/alert-definitions/{foreign_id}", {"enabled": False}),
                    ("DELETE", f"/alert-definitions/{foreign_id}", None),
                ):
                    denied, _ = request(page, url, method, path, payload)
                    assert denied.status == 404, f"Foreign {method} returned {denied.status}"
                for path in ("/runs", "/logs", "/deliveries"):
                    denied, _ = request(page, url, "GET", path)
                    assert denied.status == 403, f"Regular {path} returned {denied.status}"
                denied, _ = request(page, url, "POST", "/alert-definitions", body | {"owner_id": template["owner_id"]})
                assert denied.status == 422
            pages[0].reload(wait_until="networkidle")
            row = pages[0].locator("table.table tbody tr").first
            row.wait_for()
            pages[0].screenshot(path=artifacts / "03-private-alert.png", full_page=True)
            before = row.locator('input[type="checkbox"]').is_checked()
            row.locator('input[type="checkbox"]').click()
            pages[0].get_by_text("off" if before else "on", exact=True).wait_for()
            response, changed = request(pages[0], url, "GET", f"/alert-definitions/{ids[0]}")
            assert response.status == 200 and changed["enabled"] != before
            row.locator('input[type="checkbox"]').click()
            pages[0].get_by_text("on" if before else "off", exact=True).wait_for()
            response, restored = request(pages[0], url, "GET", f"/alert-definitions/{ids[0]}")
            assert response.status == 200 and restored["enabled"] == before
            trace["steps"].append("Both accounts created the same alert name; foreign reads and mutations returned 404. A user toggled an alert and restored it through the UI.")

            response, admin_list = request(admin_page, url, "GET", "/alert-definitions")
            assert response.status == 200 and {ids[0], ids[1]} <= {d["id"] for d in admin_list}
            pages[0].get_by_role("button", name="Log out").click()
            pages[0].get_by_role("button", name="Log in").wait_for()
            denied, _ = request(pages[0], url, "GET", "/alert-definitions")
            assert denied.status == 401
            pages[0].screenshot(path=artifacts / "04-logout.png", full_page=True)
            trace["steps"].append("Admin saw both accounts; logout invalidated the first account's session.")
        finally:
            browser.close()
    (artifacts / "trace.json").write_text(json.dumps(trace, indent=2) + "\n")
    print(f"Browser proof written to {artifacts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    verify(args.url.rstrip("/"), args.artifacts)
