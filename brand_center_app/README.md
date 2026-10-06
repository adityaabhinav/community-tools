# brand_center_app

A DoorDash Brand Center-style app backed by ThoughtSpot.

- **Analytics** -- embeds liveboard `730b7e69-...` with the ThoughtSpot Visual Embed SDK.
- **Download reports** -- choose one of three liveboards (`3ddbaa58-...`, `993fb55d-...`, `2758cc88-...`),
  add a Country filter and download CSV (ZIP of CSVs when the liveboard has several visualizations)
  without opening the liveboard. Downloaded reports are listed in a history table.

## Run
```
export TS_HOST=https://ps-internal.thoughtspot.cloud
export TS_USERNAME=...  TS_PASSWORD=...     # or TS_SECRET_KEY
export TS_COUNTRY_COLUMN=Country            # exact column name in the liveboards' data
python3 server.py                           # http://localhost:8080
```
`TS_MOCK=1 python3 server.py` runs with fake data.

## ThoughtSpot setup required for the embed
In ThoughtSpot **Develop > Security settings**, add your app origin (e.g. `http://localhost:8080`) to
both the CSP *visual embed hosts* and *CORS* allowlists, otherwise the iframe is blocked.

## Notes
- All app users act as the single server-side ThoughtSpot user. For per-user data security, mint
  tokens per signed-in user (trusted auth) in `/api/embed-token` and the export calls.
- Only the three configured liveboards can be exported.
