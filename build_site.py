# -*- coding: utf-8 -*-
"""
Build a STATIC version of the FaLXi Trend Terminal into site/index.html.

Runs the same engine (signals.py via dashboard.build_state), embeds the
resulting JSON straight into the page, and writes a self-contained HTML file.
Meant to run once a day from GitHub Actions after the daily close, then be
published to GitHub Pages — a free, always-on website with no live server.

Run:  py build_site.py
"""
import json, os, sys

import dashboard as D

def main():
    state = D.build_state()
    inject = f'<script>window.__DATA__={json.dumps(state)};</script>\n<script>'
    page = D.PAGE.replace('await(await fetch("/api/state")).json()', "window.__DATA__")
    assert "window.__DATA__" in page, "fetch call not found — dashboard.PAGE changed?"
    page = page.replace("<script>", inject, 1)
    # static page: no point auto-refreshing against embedded data
    page = page.replace("setInterval(load, 10*60*1000);", "")

    os.makedirs("site", exist_ok=True)
    out = os.path.join("site", "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    n_ok = sum(1 for i in state["instruments"] if "error" not in i)
    print(f"built {out} | instruments ok: {n_ok}/{len(state['instruments'])} "
          f"| updated {state['updated']}")
    if n_ok == 0:
        sys.exit(1)   # fail the Action rather than publish an empty page

if __name__ == "__main__":
    main()
