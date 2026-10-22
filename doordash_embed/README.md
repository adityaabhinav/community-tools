# DoorDash-style ThoughtSpot embed

Static demo app embedding a ThoughtSpot Liveboard in a DoorDash-merchant-portal-style shell
(red/white theme, pill nav, rounded cards) with DoorDash-like typography inside the liveboard.

- `index.html` / `app.css` – host page shell
- `app.js` – Visual Embed SDK `init()` + `LiveboardEmbed`, with font/colour CSS variables
- `liveboard-theme.css` – CSS loaded inside the iframe (font import + global font override)

## Run
    cd doordash_embed && python3 -m http.server 8000   # open http://localhost:8000

## Required ThoughtSpot setup
Host: `https://ps-internal.thoughtspot.cloud`, Liveboard `8930f905-38c0-4de3-b6ea-68bd9e275d93`.
In ThoughtSpot Develop > Security Settings, add the app's origin (e.g. `http://localhost:8000`)
to **CSP visual embed hosts** and **CORS whitelisted domains**, otherwise the iframe is blocked.
`liveboard-theme.css` must be served from a CSP-allowed, publicly reachable URL (localhost won't be
reachable from the cluster's browser context only if it's not your own machine; it is fine for local dev).

## Fonts
DoorDash's TT Norms Pro is proprietary; DM Sans is used as a close free stand-in. Swap the font
in `app.js` (`FONT`), `app.css`, and `liveboard-theme.css` if you have a license for the real one.

## Auth
Uses `AuthType.None` (sign in inside the iframe). Use `TrustedAuthTokenCookieless` for seamless SSO.
