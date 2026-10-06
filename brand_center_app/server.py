#!/usr/bin/env python3
"""Brand Center demo app: embedded ThoughtSpot liveboard + one-click CSV report downloads.

Reuses the ThoughtSpot client in ../liveboard_csv_download/server.py.

Environment:
  TS_HOST, TS_USERNAME, TS_PASSWORD | TS_SECRET_KEY   (see liveboard_csv_download)
  TS_COUNTRY_COLUMN   column the country filter applies to (default: Country)
  TS_MOCK=1           fake data, no cluster needed
  PORT                default 8080
"""
import os
import sys
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from urllib.error import HTTPError

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "liveboard_csv_download"))
import server as ts  # noqa: E402

ANALYTICS_LIVEBOARD = "730b7e69-ce80-4fbb-9ab8-63307b874ec5"
# Only these liveboards can be exported through this app.
REPORT_LIVEBOARDS = [
    "3ddbaa58-6845-4712-b016-122a9d01155a",
    "993fb55d-414e-4893-b211-8d3595594c1b",
    "2758cc88-f5b2-4794-982f-52b0cbbb1cf7",
]
COUNTRY_COL = os.environ.get("TS_COUNTRY_COLUMN", "Country")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
_names = {}


def report_list():
    if not _names and not ts.MOCK:
        body = {"metadata": [{"identifier": i, "type": "LIVEBOARD"} for i in REPORT_LIVEBOARDS],
                "include_visualization_headers": True}
        for it in ts.ts_call("/api/rest/2.0/metadata/search", body):
            _names[it["metadata_id"]] = (it.get("metadata_name"), len(ts._viz_headers(it)))
    out = []
    for n, i in enumerate(REPORT_LIVEBOARDS, 1):
        name, viz = _names.get(i, (None, None))
        out.append({"id": i, "name": name or f"Report {n} (mock)" if ts.MOCK else name or i,
                    "visualizations": viz or 1})
    return out


class Handler(ts.Handler):
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/api/config":
                return self._send(200, {"host": ts.HOST, "mock": ts.MOCK,
                                        "analyticsLiveboard": ANALYTICS_LIVEBOARD,
                                        "countryColumn": COUNTRY_COL})
            if u.path == "/api/reports":
                return self._send(200, report_list())
            if u.path == "/api/embed-token":
                # NOTE: every app user embeds as the server's ThoughtSpot user. For per-user
                # security, mint tokens for the signed-in user (trusted auth) instead.
                return self._send(200, {"token": "mock" if ts.MOCK else ts.get_token()})
            if u.path == "/api/download":
                lid = q["id"][0]
                if lid not in REPORT_LIVEBOARDS:
                    raise ValueError("Unknown report")
                countries = [c.strip() for c in q.get("countries", [""])[0].split(",") if c.strip()]
                filters = [(COUNTRY_COL, "IN", countries)] if countries else []
                name, ctype, data = ts.download_with_filters(lid, filters)
                return self._send(200, data, ctype,
                                  {"Content-Disposition": f'attachment; filename="{name}"'})
            path = "/index.html" if u.path == "/" else u.path
            full = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
            if not full.startswith(STATIC) or not os.path.isfile(full):
                return self._send(404, {"error": "not found"})
            with open(full, "rb") as f:
                return self._send(200, f.read(), "text/html" if full.endswith(".html") else "application/octet-stream")
        except HTTPError as e:
            self._send(502, {"error": f"ThoughtSpot returned {e.code}: {e.read().decode(errors='replace')[:300]}"})
        except (KeyError, ValueError) as e:
            self._send(400, {"error": str(e)})
        except Exception as e:
            self._send(500, {"error": str(e)})


if __name__ == "__main__":
    if not ts.MOCK and not ts.HOST:
        raise SystemExit("Set TS_HOST (or TS_MOCK=1 to try the UI with fake data)")
    port = int(os.environ.get("PORT", "8080"))
    print(f"Open http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
