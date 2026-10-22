# DoorDash-style ThoughtSpot embed

Static demo app embedding a ThoughtSpot Liveboard in a DoorDash-merchant-portal-style shell
(red/white theme, pill nav, rounded cards) with DoorDash-like typography inside the liveboard.

- `index.html` / `app.css` – host page shell
- `app.js` – Visual Embed SDK `init()` + `LiveboardEmbed`, with font/colour CSS variables
- `liveboard-theme.css` – DoorDash-style CSS loaded inside the iframe (font import + global font override)
- `liveboard-theme-facebook.css` – Facebook-style (system UI font stack) CSS loaded inside the iframe

## Run
    cd doordash_embed && python3 -m http.server 8000   # open http://localhost:8000

## Required ThoughtSpot setup
Host: `https://ps-internal.thoughtspot.cloud`, Liveboard `8930f905-38c0-4de3-b6ea-68bd9e275d93`.
In ThoughtSpot Develop > Security Settings, add the app's origin (e.g. `http://localhost:8000`)
to **CSP visual embed hosts** and **CORS whitelisted domains**, otherwise the iframe is blocked.
`liveboard-theme.css` (and the Facebook one) must be served from a CSP-allowed, publicly reachable URL (localhost won't be
reachable from the cluster's browser context only if it's not your own machine; it is fine for local dev).

## Tabs
Two liveboards, each with its own theme, selected by tab (or `?view=doordash` / `?view=facebook`):

| Tab | Liveboard | Font |
|---|---|---|
| Merchant Insights | `8930f905-38c0-4de3-b6ea-68bd9e275d93` | DM Sans (DoorDash-like) |
| Social Insights | `5a328046-8a29-4c11-ad85-52cfdf685005` | system UI stack (Facebook-like) |

## Fonts
DoorDash's TT Norms Pro is proprietary; DM Sans is used as a close free stand-in. Swap the font
in `app.js` (`FONT`), `app.css`, and `liveboard-theme.css` if you have a license for the real one.

## Auth
Uses `AuthType.None` (sign in inside the iframe). Use `TrustedAuthTokenCookieless` for seamless SSO.

## CSP note
`customCSSUrl` is loaded inside ThoughtSpot, so its host must be a trusted domain in Security Settings.
`cdn.jsdelivr.net` and `fonts.gstatic.com` are allowed by default; `localhost` or your own domain are not.
Easiest option: serve the two theme CSS files from jsDelivr (e.g. `https://cdn.jsdelivr.net/gh/<owner>/<repo>@<branch>/doordash_embed/liveboard-theme.css`, requires a public repo) and point `cssFile` in `app.js` at those URLs.
