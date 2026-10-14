# Retail Sales sample app

Embeds "Adi111's first Liveboard" (`5a328046-8a29-4c11-ad85-52cfdf685005`) with the
ThoughtSpot Visual Embed SDK.

## Run

1. `thoughtSpotHost` in `config.js` is set to `https://ps-internal.thoughtspot.cloud`.
2. Add your app's origin to the ThoughtSpot CSP and CORS allowlists (Develop > Security settings).
3. Serve the folder and open it while logged in to ThoughtSpot in the same browser:

   ```
   cd retail-sales-app && python3 -m http.server 8080
   ```

## Filter action per viz

The right-click **Filter** item on a viz is `Action.CrossFilter`. The SDK's `hiddenActions`
applies to a whole embed, so this app embeds each viz separately (`vizId`) and sets
`hiddenActions: [Action.CrossFilter]` on the ones that should not offer it. Hidden removes the
item completely; `disabledActions` would only grey it out.

Two ways to choose which vizzes keep it, set by `filterRule` in `config.js` or the URL:

- `http://localhost:8080/?rule=flag` uses `showFilter` on each viz in `vizzes`.
- `http://localhost:8080/?rule=vizId` keeps it only for the ids in `filterVizIds`.

Both give the same result today; the tab title shows which rule is active. Currently only the 4th viz
keeps the Filter action.

Note: each viz is a separate embed, so cross-filters do not carry from one viz to another.
