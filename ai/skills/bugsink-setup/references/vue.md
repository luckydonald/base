# Bugsink / Sentry — Vue frontend

Part of the `bugsink-setup` skill — see `../SKILL.md` for the shared environment-variable list, deployment wiring, and verification checklist.
This page covers the frontend-specific pieces only.

## SDK init

```ts
// src/sentry.ts
import * as Sentry from "@sentry/vue";

export function initSentry(app: VueApp, router: Router, apiBaseUrl: string): void {
  const dsn = env.VITE_SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    app, dsn,
    environment: env.VITE_SENTRY_ENVIRONMENT || undefined,
    release: env.VITE_SENTRY_RELEASE || __GIT_COMMIT_FULL__,   // see "Release/build metadata" below
    dist: __BUILD_TIME__,
    integrations: [
      Sentry.browserTracingIntegration({ router }),
      Sentry.vueIntegration({ app, tracingOptions: { trackComponents: true } }),
    ],
    sendDefaultPii: false,
    initialScope: { tags: { git_commit: __GIT_COMMIT_FULL__, git_branch: __GIT_BRANCH__, build_time: __BUILD_TIME__ } },
    tracesSampleRate: parseSampleRate(env.VITE_SENTRY_TRACES_SAMPLE_RATE) ?? 0,
  });
}
```

Add `@sentry/vue` as a runtime dependency.

## Catching errors before the Vue bundle loads

`initSentry` runs from `main.ts`, so it only exists once the whole bundle was downloaded, parsed and every import evaluated.
A bundle that fails to load (stale cache, CDN hiccup, a syntax error in an old browser) or throws while its modules evaluate is never reported by it.
Add an inline script to `index.html` that loads the Sentry browser bundle from the CDN and inits it on its own, independent of the Vue bundle.
The DSN, environment and release can't be baked in at build time then, so they are placeholders that the container replaces at start (the inline-script variant of the `VITE_SENTRY_*` variables is therefore **runtime** env, not build args):

```html
<script>
  (function () {
    var dsn = "__VITE_SENTRY_DSN__";
    if (!dsn || dsn.indexOf("__") === 0) return; // placeholder not replaced (dev): disabled
    window.__APP_SENTRY__ = true; // tells src/sentry.ts that this script already set Sentry up
    var script = document.createElement("script");
    script.src = "https://browser.sentry-cdn.com/<same version as @sentry/vue>/bundle.min.js";
    script.crossOrigin = "anonymous";
    script.async = true;
    script.onload = function () {
      var environment = "__VITE_SENTRY_ENVIRONMENT__";
      var release = "__VITE_SENTRY_RELEASE__";
      window.Sentry.init({
        dsn: dsn,
        environment: environment.indexOf("__") === 0 ? undefined : environment,
        release: release.indexOf("__") === 0 ? undefined : release,
      });
    };
    document.head.appendChild(script);
  })();
</script>
```

Hand-off, so nothing is reported twice: declare `interface Window { __APP_SENTRY__?: boolean }` in `env.d.ts` and have `initSentry` return early with `if (!dsn || window.__APP_SENTRY__) return`.
Name the flag after the project.
The trade-off is that the inline instance has no Vue/router integration, Pinia plugin, tags or tunnel, so it is the safety net for the "bundle never ran" case, not a replacement.
If the CDN script itself can't be loaded (ad blocker, offline), nothing is reported either; that is accepted.

Replace the placeholders when the container starts, with a script in the nginx image's `/docker-entrypoint.d/`:

```sh
#!/bin/sh
# Replaces the __VITE_SENTRY_*__ placeholders in index.html with the container's runtime env.
# Unset variables keep their placeholder, which index.html treats as "Sentry disabled".
set -e
INDEX=/app/index.html

# escape for the replacement side of sed s|..|..| (backslash, ampersand, delimiter)
escape() { printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'; }

for name in VITE_SENTRY_DSN VITE_SENTRY_ENVIRONMENT VITE_SENTRY_RELEASE; do
  eval "value=\${$name:-}"
  if [ -n "$value" ]; then
    sed -i "s|__${name}__|$(escape "$value")|g" "$INDEX"
    echo "40-sentry-env.sh: set $name in $INDEX"
  fi
done
```

```dockerfile
COPY --chmod=755 docker/40-sentry-env.sh /docker-entrypoint.d/40-sentry-env.sh
```

The escaping matters: a DSN contains `?` and often `&`, which `sed` would otherwise treat as "the matched text".
Default `VITE_SENTRY_RELEASE` to the platform's commit variable (`SOURCE_COMMIT` on Coolify) in the deployment config, so the inline script's events carry the same release as the bundle's.
Verify by running the image with the variables set (the DSN lands in the served `index.html`) and without them (the placeholder stays, Sentry is off).

## Enriching events

A stack trace alone often can't be traced back to its cause; attach the context that is cheap to collect and free of secrets.

**Client tags.**
Put whatever tells clients apart on the initial scope, so every event can be filtered by it.
For a Telegram Mini App: `telegram_platform` (`ios`, `android`, `tdesktop`, `weba`; `unknown` for a plain browser with the SDK loaded, `none` without it), `telegram_version` and `inside_telegram`, read from `window.Telegram?.WebApp`.
Repeat the platform as `extra` on handled errors you report yourself (`Sentry.captureException(e, { extra: { stage: 'auth-network', platform } })`), since a tag only says what the client was at init time.

**Stackless rejections.**
A promise rejected with `undefined`/`null` produces `Non-Error promise rejection captured with value: undefined`, with no stack, so every occurrence lands in one useless issue.
Tag and fingerprint those events by the route that was open, and attach the page state:

```ts
const ANONYMOUS_REJECTION = /^Non-Error promise rejection captured with value: (undefined|null)$/;

export function takePageSnapshot() {
  return {
    // Ionic marks overlays that aren't presented with `overlay-hidden`; inline ones stay mounted while closed. Adapt the selector to the UI library.
    overlays: Array.from(document.querySelectorAll('ion-modal, ion-alert, ion-popover, ion-action-sheet, ion-loading, ion-toast'))
      .filter((el) => !el.classList.contains('overlay-hidden')).map((el) => el.tagName.toLowerCase()),
    visibility_state: document.visibilityState,
    online: navigator.onLine,
    page_age_ms: Math.round(performance.now()),
  };
}

export function tagAnonymousRejection<E extends Sentry.ErrorEvent>(event: E, route: { name?: unknown; path: string; params?: object }): E {
  if (!ANONYMOUS_REJECTION.test(event.exception?.values?.[0]?.value ?? '')) return event;
  const routeName = String(route.name ?? 'unnamed');
  event.tags = { ...event.tags, anonymous_rejection: 'true', route_name: routeName, route_path: route.path };
  event.contexts = { ...event.contexts, anonymous_rejection: { route: { name: routeName, path: route.path, params: route.params ?? {} }, ...takePageSnapshot() } };
  event.fingerprint = ['anonymous-rejection', routeName]; // a recurrence on another view becomes its own issue
  return event;
}
```

Use `route.path`, never `fullPath`: the query string can hold a token.
Wire it as `beforeSend: (event) => tagAnonymousRejection(event, router.currentRoute.value)`.
Also register an `unhandledrejection` listener **before** `Sentry.init`, which `console.warn`s the route and open overlays for `undefined`/`null` reasons, so the line becomes a console breadcrumb ahead of the event; never call `preventDefault()` in it, Sentry's own handler must still report the rejection.

**Breadcrumb bursts.**
The default 100 breadcrumbs are easily filled by one second of prefetching (store actions, `fetch` calls), pushing out the click or navigation that matters.
Set `maxBreadcrumbs: 300` and collapse bursts in `beforeSend` rather than dropping them up front, so nothing is lost:
merge runs of at least 3 breadcrumbs with the same key (category plus message, or category plus method and URL without the query) whose gaps are at most 2 s into one breadcrumb at the time of the last one, with the message suffix ` (xN within T s)` and `count`/`first_timestamp`/`last_timestamp` in `data`.
Never collapse `ui.*` (clicks) or `navigation` breadcrumbs, and don't mutate the input array.
Keep it a pure exported function (`collapseBreadcrumbs(breadcrumbs, gapSeconds = 2, minRun = 3)`) so it is unit-testable.

**Tokens.**
Never log a JWT, `config.headers` or a whole axios config: console logging becomes breadcrumbs and ends up in every event.
Log a redacted form instead (head and tail of the unsigned part plus the length, never the signature) together with the decoded, non-secret claims (scopes, expiry), and set it as a Sentry context (`Sentry.setContext('auth_token', …)`) when the token changes.

## Release/build metadata

`__GIT_COMMIT_FULL__`/`__GIT_BRANCH__`/`__BUILD_TIME__` are compile-time globals injected via Vite's `define`, resolved with the same env-override → git → baked-file fallback chain used on the backend (see `python.md`'s "Release/build metadata" section — keep both sides in sync so a single deploy reports the same tags from both ends):

```js
// vite.config
function getBuildInfo() {
  const sourceCommit = process.env.SOURCE_COMMIT || ''
  try {
    return {
      commit: sourceCommit || execSync('git rev-parse HEAD', { encoding: 'utf8' }).trim(),
      branch: process.env.GIT_BRANCH || execSync('git rev-parse --abbrev-ref HEAD', { encoding: 'utf8' }).trim(),
    }
  } catch {
    // git binary unavailable (Docker build) — fall back to files baked in by a git-aware build stage
    return {
      commit: sourceCommit || readFile('git-commit.txt') || 'unknown',
      branch: process.env.GIT_BRANCH || readFile('git-branch.txt') || 'unknown',
    }
  }
}
// define: { __GIT_COMMIT_FULL__: JSON.stringify(buildInfo.commit), ... }
```

## The tunnel (self-hosted Bugsink only)

Skip this section entirely if Bugsink/Sentry is reachable directly from the browser with working CORS.
Build it whenever the backend half (see `python.md`'s "The tunnel" section) is in place — this is the frontend half that decides when to use it.

Don't hard-wire the tunnel on or off; probe first so the setup degrades gracefully whether Bugsink is reachable directly or not:

1. On init, POST an empty body straight to the DSN's envelope URL. If that succeeds, use the DSN directly — no tunnel overhead.
2. If it fails, POST to the tunnel endpoint instead (the path the backend mounted, e.g. `/api/v1/sentry/tunnel`).
   If that works, re-init Sentry with `tunnel: '<that path>'` added to the options.
3. Log both checks (`console.info`/`console.warn`) — this is the single fastest way to diagnose "no errors showing up in Bugsink" during setup, since a silently-dropped browser event otherwise looks identical to "no errors happened."

```ts
async function probeConnection(label: string, url: string): Promise<boolean> {
  try {
    const response = await fetch(url, { method: "POST", mode: "cors", body: "" });
    if (!response.ok && response.status !== 400) throw new Error(`HTTP ${response.status}`);
    console.info(`sentry connection check: ${label} - OK`);
    return true;
  } catch (e) {
    console.warn(`sentry connection check: ${label} - ERROR: ${e instanceof Error ? e.message : String(e)}`);
    return false;
  }
}
```

If the API base URL can change at runtime (e.g. the user points the app at a different backend), re-run the probe when it changes rather than only at startup.

## Pinia state scrubbing

If this project uses Pinia, add a state-scrubbing plugin before wiring `Sentry.createSentryPiniaPlugin` in — captured store state is otherwise attached to every event verbatim, including auth tokens and any other secrets sitting in the store:

```ts
export function sentryPiniaPlugin() {
  return Sentry.createSentryPiniaPlugin({
    stateTransformer: (state) => {
      const { accessToken, refreshToken, /* ...other secrets... */, ...safe } = state;
      return safe; // also collapse any large arrays to just a count if they bloat the payload
    },
  });
}
```

Get this list from whatever the store actually holds — grep the Pinia store for token/secret/credential-shaped keys rather than guessing.
Register it with `pinia.use(sentryPiniaPlugin())`.

## Sourcemap upload (recommended, optional)

Without sourcemaps, stack traces in Bugsink show minified code — useless for debugging.
`@sentry/vite-plugin` uploads them automatically on build:

```js
// vite.config
import { sentryVitePlugin } from '@sentry/vite-plugin'
// ...
plugins: [
  // gate on non-VITE_-prefixed build secrets so a build without them
  // (local dev, CI without credentials) still succeeds — just without upload
  env.BUILD_BUGSINK_URL && env.BUILD_BUGSINK_AUTH_TOKEN
    ? sentryVitePlugin({
        url: env.BUILD_BUGSINK_URL,
        authToken: env.BUILD_BUGSINK_AUTH_TOKEN,
        org: 'none',              // Bugsink has no orgs; any non-empty string is accepted
        project: env.BUILD_BUGSINK_PROJECT_SLUG,
        release: { name: buildInfo.commit, create: false, finalize: false, inject: true },
        sourcemaps: { filesToDeleteAfterUpload: ['./dist/**/*.map'] },
      })
    : null,
],
build: { sourcemap: true },
```

`BUILD_BUGSINK_URL`/`BUILD_BUGSINK_AUTH_TOKEN`/`BUILD_BUGSINK_PROJECT_SLUG` are deliberately **not** `VITE_`-prefixed — a `VITE_` prefix means Vite inlines the value into the shipped client bundle, which would leak the upload auth token to every visitor.
Keep them build-time-only secrets, and delete the local `.map` files after a successful upload so they aren't served publicly alongside the JS.

## Sample-error test view

Add a route that isn't linked from normal navigation, so you (and later, anyone running a Bugsink triage) can confirm the frontend side of the pipeline works end to end without waiting for a real bug:

```vue
<script setup lang="ts">
onMounted(async () => {
  try { await http.get("/sample-error"); } catch { /* expected */ }
  setTimeout(() => { throw new Error("frontend sample error for Sentry/Bugsink verification"); }, 0);
});
</script>
```

Word the message recognizably (contains "sample error ... for ... verification") — anyone triaging Bugsink later needs to be able to tell this apart from a real bug at a glance rather than investigate it.
