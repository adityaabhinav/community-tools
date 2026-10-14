# Retail Sales sample app

Embeds "Adi111's first Liveboard" (`5a328046-8a29-4c11-ad85-52cfdf685005`) with the
ThoughtSpot Visual Embed SDK.

## Run

1. Set `thoughtSpotHost` in `config.js`.
2. Add your app's origin to the ThoughtSpot CSP and CORS allowlists (Develop > Security settings).
3. Serve the folder and open it while logged in to ThoughtSpot in the same browser:

   ```
   cd retail-sales-app && python3 -m http.server 8080
   ```

## Filters on every viz except the first

Liveboard filters apply to all vizzes by default. The embed sets
`isScopedLiveboardFilteringEnabled: true`, which lets a filter be scoped to a group of vizzes.
One-time setup in the liveboard itself (as an editor):

1. Edit the liveboard and add a filter (e.g. Zip Code, Date or Product).
2. Scope it to the vizzes below, leaving out the first one:
   - Total sales by Monthly date
   - Total quantity purchased by Monthly date
   - the untitled fourth viz
3. Save. "Total Sales Amt by Zip Code" is unaffected when users change the filter.

Requires SDK 1.53.0+ and ThoughtSpot 26.10.0.cl+ (your cluster is 26.11.0.cl).
