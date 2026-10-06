# liveboard_csv_download

Pick a ThoughtSpot liveboard, set optional **Date range** and **Product** filters, and download the
data as CSV in one click -- without opening the liveboard.

Each visualization is exported through `POST /api/rest/2.0/report/liveboard` (CSV, with `runtime_filter`).
One visualization returns a `.csv`; several are returned as a `.zip` of CSVs (the API exports CSV one
visualization at a time).

## Run
```
export TS_HOST=https://ps-internal.thoughtspot.cloud
export TS_USERNAME=you@example.com
export TS_PASSWORD=...            # or TS_SECRET_KEY=... for trusted auth
export TS_DATE_COLUMN=Date        # column names as they appear in your liveboard's worksheet
export TS_PRODUCT_COLUMN=Product
python3 server.py                 # http://localhost:8080
```
Try the UI without a cluster: `TS_MOCK=1 python3 server.py`.

## Notes
- Filter columns must exist in the liveboard's underlying data; visualizations that lack them may ignore
  the filter or fail to export (failed tiles are skipped).
- Dates are sent as UTC epoch seconds, inclusive of the end day.
- Credentials stay on the server; the browser only talks to this proxy.
