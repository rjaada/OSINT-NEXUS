# OSINT Nexus code review — 20 September 2026

Reviewed the current `preview` working tree, including pre-existing uncommitted changes. The follow-up includes the reviewed project changes in `preview` and extends CI to run backend, frontend, media-hook and backup tests. Backend, frontend and media-hook images were rebuilt and started locally.

## Confirmed defects fixed

| Priority | Finding and root cause | Change |
|---|---|---|
| High | v2 routes read separate legacy `state.py` objects while ingestion updates `main.py`; graph state was never synchronized. | Resolve runtime values from the running application. Health now exposes actual connector configuration rather than inferring it from zero counters. |
| High | Page protection accepted cookie claims when backend verification was absent or failed. | Require a verified backend session and role; bound verification requests with timeouts. Backend authorization remains independently enforced. |
| High | PDF endpoint was outside the page proxy and launched Chromium without authentication. | Verify session and analyst/admin role, enforce CSRF, render through a trusted local origin, validate stored payload keys. |
| High | Local media could be deleted after analysis when a request supplied both its path and URL. Remote downloads had no cap, and arbitrary local paths were accepted. | Delete only hook-owned temporary downloads, restrict local paths to media storage, stream with a 50 MB limit, reject private DNS answers, clean failed downloads. |
| High | Frontend and Python dependencies had known security advisories. | Next.js 16.3.5, MapLibre 6.10.0, compatible transitive patches, python-dotenv 1.2.2, yt-dlp 2026.7.4. Adapt MapLibre's module import and explicitly serve its v6 module worker/shared bundle; otherwise production renders a blank canvas despite a successful build. Trigger event-marker rendering when the initial map or replacement style becomes ready. |
| Medium | Logins for the same user within one second produced identical signed sessions. | Add a random signed nonce per login; retain verification compatibility with existing signed tokens. |
| Medium | Runtime-hardening tests initialized the application database despite claiming SQLite isolation. | Remove unnecessary database initialization; add explicit test-database guards to database tests. |
| Medium | Missing OCR/STT capability markers were scored as claim evidence. | Ignore diagnostic markers while retaining genuine extracted text. |
| Medium | Calibration treated lack of corroboration as proof of falsity; unrelated sensors or the original event could corroborate a claim. | Leave absent evidence unresolved; exclude the original event and require matching event type for sensor candidates. |
| Medium | Prediction statistics put a SQL placeholder inside an interval literal and silently returned fallback values. | Parameterize interval multiplication; exercise the real query against isolated PostgreSQL. |
| Medium | Press-brief route rejected requests without Groq even though the shared client supports Ollama fallback. | Let the shared client choose its available provider. |
| Medium | Browser requests and media links pointed at the user's localhost; WebSocket defaults differed across pages. | Same-origin HTTP proxy by default, configurable API base, common WebSocket URL resolution and a WebSocket rewrite. |
| Medium | Standalone frontend image omitted dynamically loaded Playwright files. | Explicitly include Playwright and Playwright Core in the runtime image. Verified by real PDF export. |
| Medium | Satellite metadata comparisons were labelled ground-change/smoke detection; keyword overlap was presented as forecast accuracy. | Label both as heuristics and explain their limits; update README claims. |
| Medium | Compose depends on media-hook source that Git ignored. | Remove the ignore rule. Include the source files in the preview commit. |
| High | The header always fell back to hardcoded military headlines and preloaded fictional tracked assets. Search also linked to deleted v1 routes. | Use timestamped event-feed headlines or an explicit empty state, remove fictional asset defaults and obsolete links. |
| Low | `npm run lint` invoked an absent ESLint installation/configuration. | Add ESLint and a TypeScript parser with a focused correctness ruleset. This is not a full React accessibility/hooks lint audit. |

Existing registration privilege restrictions, idle-session expiration, role-change rejection, TOTP replay protection, graph reconnection and backup safeguards passed the available regression tests. These pre-existing changes were preserved; they are not all newly authored in this review.

## Verification

- Backend: **50 tests passed**, including auth, schema, command composition, graph recovery, runtime state, media evidence, calibration and local AI fallback. PostgreSQL integration tests used `osint_test`.
- Media hooks: **5 tests passed**, including preservation of stored media, path restrictions, private DNS rejection, oversized downloads and cleanup.
- Backup scripts: **2 tests passed**.
- Frontend: **9 regression tests passed**, lint passed, TypeScript passed, production builds passed.
- Live API smoke checks: **23/23 passed** with a real configured admin session. Checked auth, system, health, events, alerts, sources, graph, hypotheses, network, narrative, SITREP/latest/history/statistics, escalation, synchrony, SIGACT, doctrine, baseline, calibration, command snapshot, replay bounds and admin users.
- Live health returned nonzero ADS-B/AIS/FIRMS activity and all three configured. Graph returned `backend=neo4j`, with 113 nodes in the sampled response.
- Browser: **22 English/Arabic pages** returned 200 without redirecting to login and without uncaught JavaScript errors. The Operations map was additionally checked visually: actual tiles and conflict overlays rendered after fixing the v6 worker bundle. Final check counted 59 rendered markers (including event and zone markers), with no JavaScript errors. The temporary review session was logged out and cookie files removed.
- PDF: anonymous request rejected with 401; authenticated export returned 200, a `%PDF` signature and 619,403 bytes.
- WebSocket: received a message through the frontend's `/ws/live/v2` proxy.
- Frontend npm audit: **zero known vulnerabilities** after upgrades, including the added lint tooling.
- Rebuilt main backend Python environment: **zero known vulnerabilities** from pip-audit. This is not a claim about every Docker OS package, the media-model dependency tree, the unused landing application or GitHub's default branch.

## Remaining limits and follow-up work

1. Red Alert/OREF blocks this deployment IP. The application backs off and exposes stale/degraded status. Code changes cannot restore geographic access.
2. Forecast scoring remains keyword matching, not truth verification. Satellite comparison remains cloud/catalog metadata, not pixel analysis. Deepfake scoring is a video-quality heuristic, not a forensic authenticity model.
3. Historical calibration outcomes already written under the former rules were not rewritten. They need an explicit migration/reassessment before historical scores can be treated as comparable to new outcomes.
4. New calibration rules reduce false certainty but still use proxy corroboration. Matching type and distance alone do not establish the truth of an event.
5. Media DNS validation rejects private resolved addresses but does not pin the validated address through the subsequent HTTP connection. DNS-rebinding defense and strict network egress restrictions remain hardening work.
6. Hardware passkey enrollment, model accuracy, real OCR/transcription quality, satellite providers, all external-source outages and sustained concurrency were not exhaustively tested. Passing smoke checks demonstrates routing/rendering and sampled data flows, not universal correctness.
7. Review/test changes and the user's pre-existing work remain uncommitted. No security-sensitive commit or push was made. CI was not changed or rerun.

## Recommended next feature: autonomous evidence investigation

Build a bounded investigation loop on top of the existing Hypothesis Board, claim lineage and Command snapshot:

1. Turn a question into explicit competing hypotheses and falsifiable criteria.
2. Identify the evidence that would distinguish them and rank collection tasks by expected information value.
3. Retrieve from approved public sources; preserve original text/media, acquisition time, content hash and upstream provenance.
4. Attach exact supporting and contradicting passages to each claim. Reposts of one origin count as one source, not independent confirmation.
5. Revise the assessment only when attributable evidence changes it. Show what changed, what remains unknown and why collection stopped.
6. Evaluate on labelled historical cases using a cutoff time: measure citation support, unsupported-claim rate, detection lead time, false alarms and properly resolved forecast calibration. Do not use the system's own prose as ground truth.

Example product behavior: “These six reports trace back to one original source. We still lack independent evidence. Here are the two specific checks that would resolve the question.”

This is a proposed architecture for this codebase, not an already implemented capability. Active retrieval research provides a relevant foundation ([FLARE paper](https://arxiv.org/abs/2305.06983)); the [CRAG benchmark](https://github.com/facebookresearch/CRAG/) is useful for designing evaluations that distinguish supported answers, missing evidence and incorrect answers. Neither establishes that this application currently meets those benchmarks.

Dependency advisory references: [MapLibre attribution sanitizer bypass](https://github.com/advisories/GHSA-jrc7-96c5-q579), [Next.js advisory](https://github.com/advisories/GHSA-2xp9-vwfh-vxw4). Actual applicability varies by enabled feature; audit severity alone is not proof of exploitation.
