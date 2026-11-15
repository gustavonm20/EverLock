# EverLock — Progress Report

*Prepared 15 November 2026. Covers planning through version 0.16.1 (published) and 0.18.0 (local, unpublished).*

## 1. Executive summary

EverLock is a **local access-control simulator**. A virtual door with a virtual lock (shown as
"Porta 01" in the app) is opened and locked by software rules. Power, battery, network
links and sensors are simulated too. The project grew in short, documented increments. It went
from a door simulator to a system with accounts, remote commands, consent-based identities,
local OpenCV face recognition with encrypted face templates, face login, evaluation
tooling, diagnostics, backups and optional n8n alerts.

**Where it stands**

- **Published:** version **0.16.1** is on `main` in GitHub through
  [PR #24](https://github.com/gustavonm20/EverLock/pull/24), merged on 15 Oct 2026. Its
  [CI run](https://github.com/gustavonm20/EverLock/actions/runs/38689712930) passed both jobs.
  The ZIP supplied for this review contains exactly that version.
- **Reproduced locally:** **305 general tests** and **16 browser journeys** pass against the ZIP
  on this machine, and Ruff is clean.
- **New, local only:** this review adds version **0.18.0**. It has a facial access point that
  shows every decision clearly and records it. A person can now enroll their own face for door
  access. The interface was also refreshed. With the test that uses the real OpenCV models,
  0.18.0 passes **324 general tests and 19 browser journeys**. It has **not** been pushed to
  GitHub or synced to Notion.
- **Never independently validated:** the project has no real-world validation yet. No one has
  measured facial-recognition accuracy, real-camera behaviour, liveness or physical power
  continuity. Passing synthetic tests does not establish any of these.

## 2. Original goals

The planning documents ([planning.md](planning.md), [roadmap.md](roadmap.md),
[decisions.md](decisions.md) items 1–8) set these goals:

1. A **fully virtual** door, lock and sensors. The one physical purchase is a UPS
   (*nobreak*) that only powers the computer. EverLock must not monitor or control it.
2. A local Python application with a browser interface in Portuguese. No paid services.
3. Server-side rules: a 3-virtual-second release never opens the door by itself, and a
   restart never repeats an old release or command.
4. People and permissions, an audit history, remote commands with deadlines, and simulated
   connectivity failures.
5. Facial recognition with **consent, retention, revocation and encryption**. Real recognition
   and prepared (simulated) results must stay clearly separate.
6. Honest validation. Implementation and synthetic tests must never be presented as human or
   real-world acceptance.

In this codebase the "turnstile" of the brief is the **virtual door lock** of "Porta 01".
There is no separate turnstile model. This review keeps that scope and adds no physical
hardware integration.

## 3. Sources and what could be checked

| Source | Accessible? | Notes |
|---|---|---|
| Supplied archive (`EverLock-main3.zip`, 1,548,172 bytes) | Yes | Contains `EverLock-main/`, version **0.16.1**. The brief expected `EverLock-0.17.0-local.zip`, with a status file reporting 0.17.0. That is **not** what was supplied (see §6). |
| GitHub repository [gustavonm20/EverLock](https://github.com/gustavonm20/EverLock) | Yes (public API, read-only) | PRs, CI runs, issues and the `main` files were checked. The latest commit is `8aaa905` (merge of #24, 15 Oct 2026, 06:05 UTC). There are no releases or tags. |
| GitHub project board [projects/3](https://github.com/users/gustavonm20/projects/3) | **No** | Returns HTTP 404 without sign-in. |
| Notion pages ([hub](https://app.notion.com/p/3e8e2dde06ab809c893fcbd6a4958ff8), [plan](https://app.notion.com/p/3e7e2dde06ab81f68b2ece96ce4a61a2), [board](https://app.notion.com/p/90252045d9ab497b8b17c0b40b78567c)) | **No** | Each shows a sign-in page for the "Espaço de Projeto expotech" workspace. Notion claims in this report come only from references inside the repository. |

## 4. Status levels used in this report

| Level | Meaning |
|---|---|
| **Planned** | Described in the planning, roadmap or decision documents. |
| **Implemented locally** | The code exists in a local copy. |
| **Tested** | Automated tests pass. These use isolated databases, synthetic accounts, and a fake face engine or generated frames. |
| **Merged / published** | On GitHub `main` through a PR with a passing CI run. |
| **Independently validated** | Checked with real people, a real camera, real e-mail or n8n delivery, or real hardware. **Nothing in the project is at this level yet.** |

## 5. Timeline

Dates come from `docs/status.md` unless a GitHub timestamp is given. Test counts are the
project's own records, except where marked as reproduced in this review.

| Increment | Date | What was delivered | Evidence | Level reached |
|---|---|---|---|---|
| Planning | Sept 2026 | Virtual-only scope, Python/FastAPI/SQLite, server-side rules, UPS without integration (decision 12, 28 Sep) | [planning.md](planning.md), [decisions.md](decisions.md); Notion board referenced, not accessible | Planned |
| Base, door, history | to 27 Sep | Virtual door and lock, 3 s release, manual exit and key, persistent history, safe restart | PRs #14 and #16 merged 27 Sep; #17 and #18 merged 28 Sep | Published |
| 0.3 | ~27 Sep | Energy in Wh, unified virtual clock, light/dark theme, login, roles, sessions | 101 tests (status.md); [CI run 36295870556](https://github.com/gustavonm20/EverLock/actions/runs/36295870556), not re-checked here | Published |
| 0.4 | ~28 Sep | Remote commands with deadlines, duplicate and conflict handling, internet/LAN/power failures | 116 tests (status.md) | Published* |
| 0.5 | 29 Sep | Identities separate from accounts: versioned consent, revocation, retention, schedules, **simulated** recognition | 149 tests (status.md) | Published* |
| E-mail accounts / account types | 29–30 Sep | E-mail confirmation and single-use admin invites | 159 tests, plus 38 focused tests | Published* |
| 0.6 | 1 Oct | OpenCV YuNet + SFace pipeline; AES-256-GCM encrypted templates; no images stored | 181 tests; the real engine **did not run** at the time (models unreachable) | Published* |
| 0.7 – 0.12 | 2–3 Oct | Face login, n8n webhook, password reset, model auto-download, backups, history filters and CSV, head-turn challenge before door release | 194 → 238 tests (status.md) | Published* |
| 0.13 | 3 Oct | Cancellation fixes, evaluation tool (`avaliar_rostos.py`), integrated scenarios | 271 tests; [PR #20](https://github.com/gustavonm20/EverLock/pull/20) merged 3 Oct | Published |
| 0.14 | "04/10" in status.md | Admin diagnostics page; first Playwright browser journeys | [PR #21](https://github.com/gustavonm20/EverLock/pull/21) merged **13 Oct** (see §6) | Published |
| 0.15 | 13 Oct | Central migrations, cursor pagination, 16 MiB request limit, durable notification outbox, grouped navigation | 300 tests + 8 journeys; [PR #22](https://github.com/gustavonm20/EverLock/pull/22) merged 14 Oct | Published |
| 0.16 | 15 Oct | Evaluation prep (`--check-only`, batched reads), camera lifecycle fixes | [PR #23](https://github.com/gustavonm20/EverLock/pull/23); [CI run 38686568687](https://github.com/gustavonm20/EverLock/actions/runs/38686568687) success | Published |
| **0.16.1** | 15 Oct | Approved visual finish (150 ms transitions, capture indicator, reduced motion) | [PR #24](https://github.com/gustavonm20/EverLock/pull/24); [CI run 38689712930](https://github.com/gustavonm20/EverLock/actions/runs/38689712930) success, both jobs. **Reproduced here: 305 + 16 pass** | **Published** (current baseline) |
| **0.18.0** | 15 Nov | Facial access point, complete decision logging, self-service door enrollment, visual refresh | 324 general tests + 19 browser journeys pass locally (§7) | **Implemented locally and tested; not published** |

\* For 0.4–0.12 there are no separate PRs. The only merged PRs are #14, #16, #17 and #18
(27–28 Sep), then PR #20 (3 Oct). This work therefore appears to have reached `main`
through PR #20, but that was not traced commit by commit.

**Open items on GitHub:** issues #3, #4, #7–#13. Issue #13 is the test-client deprecation
warning, which still appears. PR #19 ("Update README") is still open.

## 6. Supplied ZIP compared with GitHub, and discrepancies

| Point | Brief | What the sources show |
|---|---|---|
| Archive version | `EverLock-0.17.0-local.zip`; status.md reports 0.17.0 local | Supplied file is `EverLock-main3.zip`, version **0.16.1** (`pyproject.toml`, `__init__.py`, UI). Its `docs/status.md` matches GitHub `main` byte for byte, apart from line endings. **No "0.17" exists in the ZIP or on GitHub.** |
| Baseline test counts | 305 general tests and 16 browser journeys | status.md says **305 + 11** for 0.16 (PR #23, run 38686568687) and **16** journeys locally for 0.16.1. "305 + 16" appears only in the **PR #24 description**. This review re-ran the ZIP: **305 passed, 16 passed.** |
| 0.14 date | — | status.md gives 04/10 for the increment; PR #21 merged on 13 Oct. Likely the date of local work versus the date of merge. |
| Notion / project board | Hub, plan and delivery board | Not accessible. Their content (18 tasks, Kanban) is known only from repository references. |

To avoid a clash with a possible local 0.17.0 that was not supplied, this review numbers its
changes **0.18.0**. If no 0.17.0 exists, renumber before publishing.

## 7. What this review added (0.18.0, local)

**Design.** A new `refresh.css`, loaded last, raises small text to at least 12 px for labels
and 13–14 px for reading text. Some text was previously as small as 7–10 px, and mobile rules
made it smaller still. It also unifies focus rings, button states and card surfaces, and adds
semantic colours for granted and denied in both themes. Reduced motion is respected. Outdated
"face recognition is in preparation" messages were corrected.

**Facial access point** (Overview page, operated by an administrator session):

- camera frame with a framing guide;
- a four-step indicator (front → turn → local analysis → decision);
- a large **Access granted / Access denied** panel that gives the reason;
- a countdown until the lock re-engages, plus **Travar agora** (lock now);
- recent decisions and today's totals.

The simulated, camera-free test sits in a clearly labelled "Laboratório" area.

**Every attempt ends in a recorded decision, and the lock stays engaged unless authorised.**
Before 0.18.0, several outcomes left no trace in the history: low-quality captures,
cancellations, expired challenges, a missing engine, unexpected OpenCV failures, and the
operator's session ending mid-analysis. Each now produces a `recognition_*` event and a
response with a stable `decision` object.

**Self-service door enrollment.** This implements the item that [decision 13](decisions.md)
deferred: consent given by the person themself. An admin links an identity to an active
account. Under *Conta › Meu acesso pela porta*, that person can then:

- read the consent text and record their own acceptance;
- confirm their password and capture 5 photos;
- delete the enrollment or revoke consent.

Schedule, retention and active status stay with the admin. A deactivated linked account is
refused at the door (`account_inactive`). The database migration from schema 2 to 3 only
adds columns. It was also exercised on a real (throwaway) database.

**Test mode kept separate from normal use.** The server reports which face engine is running
(`engine_kind`: `opencv`, `unavailable` or `test_double`). Diagnostics and the access point
display a "test engine" warning whenever a test double is injected. Normal startup always
builds the OpenCV engine.

## 8. Facial recognition → lock: evidence

Normal flow, all on the server:

1. Images come from the browser camera.
2. `OpenCVFaceEngine` (YuNet + SFace) reads them, after the head-turn check.
3. Similarity and ambiguity are checked.
4. `identities.evaluate()` checks consent, retention, active status, linked account and
   schedule.
5. The controller's door rules are applied.
6. The lock releases for 3 virtual seconds and then re-locks automatically.

Authorisation and actuation happen only in the backend. A regular account gets 403 from
recognition, identities and direct unlock.

| Requirement | Automated evidence (`tests/test_face_access_flow.py`, `tests/browser/test_face_access_point.py`) |
|---|---|
| 1. Own-face enrollment through consent | API: link → consent → password → 5 captures. Browser: the same flow in *Conta*. Wrong password gives 403; missing consent gives 409. |
| 2. Real pipeline in normal use | `create_app()` with no arguments builds `OpenCVFaceEngine` for both the door and face login, and reports `engine_kind: "opencv"`. The product package contains no test double or canned match. **The real YuNet/SFace models were loaded**: computer-generated non-face frames went through them and every one was rejected, with the lock engaged. |
| 3. Server-side authorisation | Revoked (templates deleted), expired retention (purged), inactive identity, inactive account and out-of-schedule cases all deny. So do ambiguity and quality rejection. |
| 4. Release, then safe re-lock | Granted gives `lock: released` and `release_seconds: 3`. At 2.9 virtual seconds the lock is still released; after 3 s it is engaged. Open-then-close also re-locks. The browser journey sees *Liberada* → *Engatada* with no user action. |
| 5. Everything else stays locked | Covered: unknown, ambiguous, revoked, expired, inactive, out-of-schedule, low quality (4 kinds), cancelled, expired challenge, missing models, OpenCV exception, engine lost mid-analysis, door open. Each asserts that the door is secured and that no `unlock` event exists. |
| 6. Clear UI and private history | The browser shows *Acesso liberado* / *Acesso negado* with the reason. Events and CSV contain `#id` and reason codes, never labels, images or template bytes. |
| 7. Manual lock and recovery | **Travar agora** (`end_release`) re-engages immediately. Existing power-loss and restart tests still pass. |

**Limits of this evidence.** The fake engine turns text markers into vectors, and the browser
camera is a generated canvas. These tests prove the software path: recognition →
authorisation → actuation → logging. They do **not** measure recognition accuracy on real
people, real-camera performance, or resistance to photos, videos or masks. The head-turn
challenge is not strong liveness detection. No person took part in any test.

## 9. Automated checks run in this review (Windows, Python 3.13.3)

| Check | Baseline 0.16.1 (ZIP) | 0.18.0 |
|---|---|---|
| Ruff | pass | pass |
| JavaScript syntax (`node --check`, every script) | — | pass |
| General suite (`pytest -q`) | **305 passed** | **324 passed** (including the real-OpenCV test; 323 + 1 skipped without models) |
| Browser journeys (`pytest tests/browser`) | **16 passed** | **19 passed** |
| Migration 2 → 3 on an existing database | — | pass |

The only warning is the httpx/TestClient deprecation tracked in issue #13. Visual checks used
screenshots at 1440 px and 390 px in light and dark themes, rendered by Playwright with a
generated camera feed.

## 10. Remaining work, limitations and next steps

**Not done in this review.** 0.18.0 is not on GitHub: there is no branch, PR or CI run yet.
Notion and the GitHub board were not updated, and could not be read.

**Known limitations.**

- Face thresholds (0.45 for the door, 0.55 for login) and turn thresholds are provisional.
- There is no strong liveness check.
- The access point needs an administrator session on the camera computer.
- The server listens only on `127.0.0.1`. Remote use would need HTTPS and a new review.
- E-mail and n8n delivery are implemented but have not been proven against real services.
- The UPS only powers the computer, by design.

**Project acceptance items still open** (as recorded in [pendencias.md](pendencias.md)):
real-image evaluation, real-camera checks, demonstration by another person, operational
checks of e-mail, backup and n8n, and the UPS continuity test. This report does not depend on
any of them and does not request them. 0.18.0 covers only the software side of "consent by
the person themself".

**Practical next steps, none requiring a person to be tested:**

1. Push 0.18.0 to a branch, open a PR using the template, and let CI run. Confirm the version
   number first (0.17.0 or 0.18.0).
2. Add a CI job that downloads the SHA-256-pinned models and runs the opt-in real-OpenCV test
   (`EVERLOCK_TEST_MODELS_DIR`).
3. Resolve issue #13 (TestClient warning) and close or merge PR #19.
4. Consider a restricted "kiosk" session scope, so that the access-point computer does not
   need a full administrator session.
5. Mirror this report and the 0.18 decisions (27 and 28) into Notion manually, if authorised.
