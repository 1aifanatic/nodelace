# Ten Nodelace samples

Generated locally through the Nodelace 0.3.0 npm API, using the shared renderer
and local Chromium. No AI image generation or remote rendering was used.

Open `index.html` in a browser. Toggle Light editorial / Dark editorial to
switch previews; each card links to both standalone HTML and high-resolution PNG.
All HTML files embed their fonts and work offline. PNGs are rendered at 2x scale.

Contents: 10 diagram sources, 20 HTML files, 20 PNG files, 20 SVG files, two gallery
overview images, and machine-readable verification results. All 20 theme variants
pass strict layout diagnostics and browser node-text bounds checks.

| Diagram | Light | Dark |
|---|---|---|
| A small web service | [HTML](rendered/01-web-service-light.html) / [PNG](rendered/01-web-service-light.png) | [HTML](rendered/01-web-service-dark.html) / [PNG](rendered/01-web-service-dark.png) |
| Orders become events | [HTML](rendered/02-event-processing-light.html) / [PNG](rendered/02-event-processing-light.png) | [HTML](rendered/02-event-processing-dark.html) / [PNG](rendered/02-event-processing-dark.png) |
| From records to insight | [HTML](rendered/03-analytics-pipeline-light.html) / [PNG](rendered/03-analytics-pipeline-light.png) | [HTML](rendered/03-analytics-pipeline-dark.html) / [PNG](rendered/03-analytics-pipeline-dark.png) |
| An assistant with context | [HTML](rendered/04-assistant-architecture-light.html) / [PNG](rendered/04-assistant-architecture-light.png) | [HTML](rendered/04-assistant-architecture-dark.html) / [PNG](rendered/04-assistant-architecture-dark.png) |
| A release with a safety gate | [HTML](rendered/05-release-gate-light.html) / [PNG](rendered/05-release-gate-light.png) | [HTML](rendered/05-release-gate-dark.html) / [PNG](rendered/05-release-gate-dark.png) |
| Route the next support ticket | [HTML](rendered/06-support-triage-light.html) / [PNG](rendered/06-support-triage-light.png) | [HTML](rendered/06-support-triage-dark.html) / [PNG](rendered/06-support-triage-dark.png) |
| A clear expense decision | [HTML](rendered/07-expense-approval-light.html) / [PNG](rendered/07-expense-approval-light.png) | [HTML](rendered/07-expense-approval-dark.html) / [PNG](rendered/07-expense-approval-dark.png) |
| Sign in, with two outcomes | [HTML](rendered/08-sign-in-sequence-light.html) / [PNG](rendered/08-sign-in-sequence-light.png) | [HTML](rendered/08-sign-in-sequence-dark.html) / [PNG](rendered/08-sign-in-sequence-dark.png) |
| Checkout and an optional receipt | [HTML](rendered/09-checkout-sequence-light.html) / [PNG](rendered/09-checkout-sequence-light.png) | [HTML](rendered/09-checkout-sequence-dark.html) / [PNG](rendered/09-checkout-sequence-dark.png) |
| A worker repeats a request | [HTML](rendered/10-worker-retry-sequence-light.html) / [PNG](rendered/10-worker-retry-sequence-light.png) | [HTML](rendered/10-worker-retry-sequence-dark.html) / [PNG](rendered/10-worker-retry-sequence-dark.png) |

Edit the `.diagram` files under `sources/` and regenerate with the project:

```sh
node npm/scripts/render-gallery.mjs
```

This helper requires npm dependencies plus Playwright and its Chromium browser.
For one file, use `npx nodelace render source.diagram --theme dark --format html`
or `npx nodelace export source.diagram -o output.png --theme dark`.
