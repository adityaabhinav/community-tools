#!/usr/bin/env python3
"""One-click liveboard -> CSV download with Date and Product filters.

Serves a small web UI and proxies ThoughtSpot REST API v2 calls so credentials
never reach the browser. Standard library only.

Configuration (environment variables):
  TS_HOST         e.g. https://ps-internal.thoughtspot.cloud   (required)
  TS_USERNAME     ThoughtSpot user                              (required)
  TS_PASSWORD     password   -- or --
  TS_SECRET_KEY   trusted-auth secret key
  TS_DATE_COLUMN     name of the date column to filter   (default: Date)
  TS_PRODUCT_COLUMN  name of the product column          (default: Product)
  TS_MOCK=1       run with fake data (no cluster needed)
  PORT            default 8080
"""
import io
import json
import os
import re
import time
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest
from urllib.error import HTTPError

HOST = os.environ.get("TS_HOST", "").rstrip("/")
MOCK = os.environ.get("TS_MOCK") == "1"
DATE_COL = os.environ.get("TS_DATE_COLUMN", "Date")
PRODUCT_COL = os.environ.get("TS_PRODUCT_COLUMN", "Product")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

_token = {"value": None, "expires": 0}


def ts_call(path, body, raw=False):
    """POST to the ThoughtSpot v2 API; returns parsed JSON (or bytes if raw)."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if not path.startswith("/api/rest/2.0/auth/"):
        headers["Authorization"] = "Bearer " + get_token()
    req = urlrequest.Request(HOST + path, json.dumps(body).encode(), headers)
    with urlrequest.urlopen(req, timeout=120) as resp:
        data = resp.read()
    return data if raw else json.loads(data)


def get_token():
    if _token["value"] and time.time() < _token["expires"] - 60:
        return _token["value"]
    body = {"username": os.environ["TS_USERNAME"], "validity_time_in_sec": 3600}
    if os.environ.get("TS_SECRET_KEY"):
        body["secret_key"] = os.environ["TS_SECRET_KEY"]
    else:
        body["password"] = os.environ["TS_PASSWORD"]
    resp = ts_call("/api/rest/2.0/auth/token/full", body)
    _token.update(value=resp["token"], expires=time.time() + 3600)
    return _token["value"]


def list_liveboards(query=""):
    if MOCK:
        items = [
            {"id": "a463b58f-aaaf-4e24-b5ec-9346bfe4ecb1", "name": "Sales Overview (mock)", "visualizations": 2},
            {"id": "mock-2", "name": "Inventory Health (mock)", "visualizations": 1},
        ]
        return [i for i in items if query.lower() in i["name"].lower()]
    body = {
        "metadata": [{"type": "LIVEBOARD"}],
        "record_size": 100,
        "include_visualization_headers": True,
        "sort_options": {"field_name": "NAME", "order": "ASC"},
    }
    if query:
        body["metadata"][0]["name_pattern"] = "%" + query + "%"
    out = []
    for it in ts_call("/api/rest/2.0/metadata/search", body):
        out.append({
            "id": it["metadata_id"],
            "name": it.get("metadata_name") or it["metadata_id"],
            "visualizations": len(_viz_headers(it)),
        })
    return out


def _viz_headers(item):
    return item.get("visualization_headers") or \
        (item.get("metadata_detail") or {}).get("visualization_headers") or []


def get_visualizations(liveboard_id):
    body = {"metadata": [{"identifier": liveboard_id, "type": "LIVEBOARD"}],
            "include_visualization_headers": True}
    items = ts_call("/api/rest/2.0/metadata/search", body)
    return [(v["id"], v.get("name") or v["id"]) for v in _viz_headers(items[0])] if items else []


def build_filters(date_from, date_to, products):
    """Runtime filters; dates are sent as epoch seconds (UTC)."""
    def epoch(d, end=False):
        dt = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp()) + (86399 if end else 0)

    f = []
    if date_from:
        f.append((DATE_COL, "GE", [str(epoch(date_from))]))
    if date_to:
        f.append((DATE_COL, "LE", [str(epoch(date_to, True))]))
    if products:
        f.append((PRODUCT_COL, "IN", products))
    return f


def download_zip_or_csv(liveboard_id, date_from, date_to, products):
    """Returns (filename, content_type, bytes)."""
    if MOCK:
        csv = f"{DATE_COL},{PRODUCT_COL},Sales\n{date_from or '2026-01-01'},{(products or ['Widget'])[0]},100\n"
        return "mock.csv", "text/csv", csv.encode()
    vizzes = get_visualizations(liveboard_id)
    if not vizzes:
        raise ValueError("Liveboard has no visualizations")
    filters = build_filters(date_from, date_to, products)
    runtime = {}
    for i, (col, op, vals) in enumerate(filters, 1):
        runtime[f"col{i}"], runtime[f"op{i}"], runtime[f"val{i}"] = col, op, vals
    files = []
    for vid, vname in vizzes:
        body = {"metadata_identifier": liveboard_id, "file_format": "CSV",
                "visualization_identifiers": [vid]}
        if runtime:
            body["runtime_filter"] = runtime
        try:
            files.append((vname, ts_call("/api/rest/2.0/report/liveboard", body, raw=True)))
        except HTTPError as e:
            # Tiles that can't export (e.g. text/notes) are skipped.
            if e.code not in (400, 404):
                raise
    if not files:
        raise ValueError("No visualization could be exported as CSV")
    if len(files) == 1:
        return _safe(files[0][0]) + ".csv", "text/csv", files[0][1]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(_safe(name) + ".csv", data)
    return "liveboard_export.zip", "application/zip", buf.getvalue()


def _safe(name):
    return re.sub(r"[^\w.\- ]+", "_", name).strip() or "export"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/api/liveboards":
                return self._send(200, list_liveboards(q.get("q", [""])[0]))
            if u.path == "/api/config":
                return self._send(200, {"dateColumn": DATE_COL, "productColumn": PRODUCT_COL})
            if u.path == "/api/download":
                products = [p.strip() for p in q.get("products", [""])[0].split(",") if p.strip()]
                name, ctype, data = download_zip_or_csv(
                    q["id"][0], q.get("from", [""])[0], q.get("to", [""])[0], products)
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
        except Exception as e:  # keep the UI informative
            self._send(500, {"error": str(e)})


if __name__ == "__main__":
    if not MOCK and not HOST:
        raise SystemExit("Set TS_HOST (or TS_MOCK=1 to try the UI with fake data)")
    port = int(os.environ.get("PORT", "8080"))
    print(f"Open http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
