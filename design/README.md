# PuckPulse brand

- `puckpulse-logo-dark.png` / `puckpulse-logo-light.png`: full logo (mark + wordmark) for
  dark and light backgrounds (resume, LinkedIn, slides).
- `puckpulse-icon-512.png`: the app icon.
- The app's own assets live in `frontend/public/`: `icon.svg` (master icon: puck on a navy
  tile, also the source of the PNG icons) and `logo-mark.svg` (the puck alone, for the header).
- Colors: brand sky blue `#22a8f2` ("Pulse", the heartbeat line), navy tile `#0b1730`,
  app background `#0a0b0f`.
- `logo-round2.html` is the design sheet the final logo came from (based on a ChatGPT
  concept, rebuilt as vector with a dark-mode variant); `logo-concepts.html` holds the first
  round of directions.

To regenerate the PNG icons after editing `icon.svg`, render it at 512, 192, and 180 px
(e.g. with a headless browser); the exact sizes are listed in `frontend/vite.config.js`.
