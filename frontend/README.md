# frontend

BookShelf's frontend is the single-page React app that people chat with. It streams each turn from the backend, showing the plan diagram, one section per step and the reply with its book cards. It also serves the about pages and, against a local backend, the review queue. How the code is laid out: [src/](src/README.md).

## Built with

| | |
|---|---|
| React 19, Vite | the app and its dev server |
| Tailwind CSS | styling, over the tokens in `src/styles/` |
| mermaid, @panzoom/panzoom | the plan diagram, with pan and zoom |
| react-markdown, highlight.js | replies, about pages and code blocks |
| Firebase Hosting, App Check | where it is deployed, and the token that proves a request came from the site |

## Set up

You need Node 20+ and the backend running with `make dev`.

```bash
make install   # npm install
make dev       # Vite on :3000, against http://localhost:8000
```

`VITE_API_URL` tells the app where the backend is. It is committed per mode: `.env.development` (localhost) is used by `make dev`, and `.env.production` (the Cloud Run URL plus the public Firebase App Check ids) is used by `make build`, so a build from a fresh clone points at the live backend. To point dev somewhere else, create `.env.local`; it is git-ignored and overrides both files.

## Commands

```bash
make dev      # dev server with hot reload
make lint     # ESLint
make build    # production build into dist/
make deploy   # build, then publish dist/ to Firebase Hosting
```

## Deploy

`make deploy` builds in production mode and runs `firebase deploy --only hosting`, which publishes to the `book-rec` target at https://tuanqpham0921.web.app. You need the Firebase CLI, logged in with `firebase login`. The site's origin must be in the backend's allowed origins (`APP_ALLOW_ORIGINS` in the backend's `config/.env.deployment`), or the browser blocks every call.
