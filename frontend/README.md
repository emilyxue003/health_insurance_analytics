# HealthPulse frontend

React 19 and Vite power the Data Explorer, Population Health, Claims Overview, and Premium Equity & SQL views.

## Saved-data demo

```sh
npm ci
npm run build:demo
npm run preview:demo
```

Open `http://127.0.0.1:5174`. The built `dist` directory contains a static app, reviewed synthetic data, SQL, result exports, and timing evidence. It has no live database connection.

For demo development, run `npm run dev` and open `http://localhost:5173/?demo=1`.

## Local MySQL dashboard

Start the configured backend on port 8001, then run `npm run dev` and open `http://localhost:5173`. `VITE_API_URL` can override the API address; the server origin must also be permitted by the backend CORS settings. The API is intended for local development.

## Checks

```sh
npm run lint
node scripts/check-errors.mjs
npm run build
npm run build:demo
node scripts/check-demo.mjs
```

The saved-data check reconciles full-source totals, SQL hashes, query evidence, connected sample foreign keys, member lookups, invalid requests, and 24 complete pagination walks. Error tests distinguish request timeouts, invalid periods, and backend failures without displaying raw private error details.

## Deployment

Run `npm run build:demo` and publish only `dist` to the existing Netlify project. Keep backend credentials, raw source CSVs, Python environments, and local authoring metadata outside the deployment. `npm run build` creates the regular API-backed build and must not be substituted for the static demo build.

The public demo is at https://healthpulse-analytics.netlify.app/. See the root README for analytical methods, data scope, and full-data benchmark limitations.
