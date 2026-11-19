# abacus-ontobricks — deployment blockers, bugs and open issues

Status as of **2026-11-16** for the `abacus` instance of OntoBricks on the
`demo-build` workspace (`1654085560780927`), branch `feat/hello-abacus` of
`github.com/alexxx-db/ontobricks`.

This document separates what is **confirmed** (observed directly, with the
evidence) from what is **assumed or unverified**. Read the "Unverified"
markers literally: they are the places a deploy can still fail.

---

## 1. TL;DR

| # | Item | Severity | Status |
| --- | --- | --- | --- |
| B1 | Workspace has **no PyPI egress** (Apps builds, serverless, classic) | Hard blocker (root cause) | Open — needs network/platform owner |
| B2 | Offline wheel artifact has **never been built** | Hard blocker | **Resolved 2026-11-17** — built off-workspace, uploaded to `/Volumes/genie_agents/internal/libraries/abacus-databricks-genie-workbench/abacus-ontobricks-python/`, verified and copied into `vendor/` + `src/mcp-server/vendor/` (see §2 B2 update) |
| B3 | `scripts/deploy.sh` **cannot run inside the workspace** | Hard blocker for in-workspace deploys | Workaround: deploy from laptop/CI |
| B4 | Post-deploy bootstrap steps (perms, Lakebase schema) **were skipped** by the manual deploy | Will break the app after it boots | **Resolved 2026-11-17** — applied by hand with user authorization, all read back (see §2 B4) |
| B5 | **App build logs are not readable** from the agent (PAT auth) | Diagnosis blocker | Read them in the Apps UI |
| I1–I12 | Unverified assumptions in the offline-install design | Risk | Listed in §5; each has a check |
| F1–F4 | Bugs found and fixed during this work | Fixed | §6 |
| T1 | Test suite only partly runnable in the workspace | Gap | Needs `ci.yml` or laptop |

**Update 2026-11-17 02:40 UTC — both apps deployed and RUNNING** from the
git folder with the vendored wheels (`bundle validate` / `bundle deploy` /
`bundle run` for each app, no `deploy.sh`):

| App | Deployment | Result |
| --- | --- | --- |
| `mcp-ontobricks-abacus` | `01f1e22dee4c1451961f4efb2617cb70` (02:23 UTC) | SUCCEEDED; offline install from `./vendor/wheels` at build; RUNNING |
| `ontobricks-abacus` | `01f1e22e1bd4103abc62154533d88b35` (02:25 UTC) | SUCCEEDED after ~12 min (source prep ~7 min, download ~4 min for the ~250 MB tree); RUNNING and still RUNNING 3+ min later |

B1 is bypassed and B2 is resolved. **Still open:** B4 (permission and
Lakebase registry bootstrap never ran — expect registry/permission errors in
the UI until it does), B5 (logs; the `/health` probe from the assistant gets
the OAuth login redirect, so the app's own health was not checked), and a
new one: the gitignored `resources/_generated_instance_target.yml` had
disappeared from the git folder between sessions (`bundle validate` reported
"dev-lakebase-abacus: no such target") and was regenerated with
`_ensure-instance-target.sh`.

**Runtime state before the redeploy** (read from the Apps API, 2026-11-16):

| App | Compute | Active deployment | Status |
| --- | --- | --- | --- |
| `ontobricks-abacus` | **ACTIVE** (running and billing) | `01f1e1fb41e21349b856321722781053`, 2026-11-16 20:21 UTC, source `/Workspace/Users/alex.baretto@abacusinsights.com/abacus-ontobricks` | **FAILED** — "Package installation failed with Databricks-managed Python constraints enabled" |
| `mcp-ontobricks-abacus` | STOPPED | none | Never started in this effort (it would fail the same way) |

Previous failed deployment of the main app: `01f1df69cbe413e0b4202eb7ba739fd7`
(2026-11-13 13:54 UTC, source `~/.bundle/ontobricks-abacus/dev-lakebase-abacus/files`).

> Cost note: `ontobricks-abacus` compute is ACTIVE while its deployment is
> FAILED, so it is billing without serving anything. Stop it until B1/B2 are
> resolved if that matters.

---

## 2. Hard blockers

### B1 — No PyPI egress from anywhere in the workspace (root cause)

Every Databricks Apps build of this app since early November fails at
package installation, regardless of what `requirements.txt` contains.

**Evidence (confirmed):**

| Where | Test | Result |
| --- | --- | --- |
| Databricks Apps build (`ontobricks-abacus`) | Deploy with `requirements.txt` = `uv` only | FAILED, "Package installation failed…" (2026-11-13 and 2026-11-16) |
| Serverless notebook | `socket.gethostbyname("pypi.org")`, `files.pythonhosted.org` | `[Errno -2] Name or service not known` (2026-11-16, twice) |
| Serverless notebook | `pip download uv` | `[Errno -3] Temporary failure in name resolution` on `/simple/uv/` |
| Classic cluster `1112-162116-297ysjlg` | DNS for `pypi.org` / `files.pythonhosted.org` | Resolves (AAAA records returned) |
| Classic cluster | IPv4 TCP connect to `pypi.org`, `files.pythonhosted.org`, `github.com` on 443 | **Timeout** after 8 s each |
| Classic cluster | `pip download uv` | `[Errno 101] Network is unreachable` (IPv6 route) |

**History (from earlier sessions, recorded 2026-11-09/10):**

* Other apps on the same workspace fail the same way since November
  (`ontos-alex-baretto`, `genie-ontology-readiness-dev`). Apps deployed
  June–September 2026 installed fine, so this is a change in the
  environment, not in OntoBricks.
* The serverless notebook `pip.conf` pointed at the Databricks package proxy
  `package-proxy.host.local` (192.168.200.14) port 8184, which **refused
  TCP** on 2026-11-09 ~20:16 UTC. External DNS was refused by resolver
  192.168.200.6.
* Apps builds show DNS errors (`Errno -3`), notebooks showed proxy refusal —
  two different symptoms of the same lack of egress.
* A support ticket was drafted on 2026-11-10.

**Root cause: NOT confirmed.** Candidates:

1. A serverless network policy (egress control) on the workspace that denies
   internet access, including the Apps build containers.
2. The Databricks-managed package proxy for this workspace is down or
   misconfigured, and the containers have no direct-internet fallback.
3. For classic compute: the customer VPC has no NAT / internet route (IPv4
   times out, IPv6 unreachable).

The hello-abacus template (`hello-abacus/scripts/build_artifact.sh`) states
that "Customer workspaces block PyPI" and that serverless has no internet
egress — i.e. this is likely **by design** for Abacus workspaces, not an
outage. If so, B1 will not be "fixed" and the offline artifact (B2) is the
permanent path.

**What is needed from the network/platform owner:**

* Confirm whether egress to PyPI is intentionally blocked for this workspace
  (serverless network policy, Apps network policy, VPC routing).
* If an internal mirror exists (Artifactory/Nexus/CodeArtifact), its URL and
  whether Apps containers can reach it. With a mirror, the whole vendoring
  approach could be replaced by an `--index-url` in `requirements.txt`.
* If intentionally blocked: nothing — proceed with B2.

### B2 — The offline wheel artifact has never been built

Because of B1, both apps were switched to the hello-abacus pattern: every
runtime dependency ships with the app as a wheel and installs with no package
index. The tooling is committed; **the wheels themselves do not exist yet**,
because building them needs PyPI, and nothing in the workspace can reach PyPI.

**What was built (committed on `feat/hello-abacus`):**

| Component | Role |
| --- | --- |
| `scripts/build_artifact.sh` | Exports `uv.lock` (main app with `--extra lakebase`), resolves for CPython 3.11 / `x86_64-manylinux_2_28`, downloads wheels with `pip download --only-binary`, builds sdist-only pins (`promise`), splits main-app wheels over 9 MiB into `.whl.partNN` chunks, writes `vendor/requirements.txt` + `lock.sha256`, then checks. `--check` verifies offline; `--force` rebuilds. |
| `scripts/_internal/_vendor_artifact.py` | `prune` (evaluates export markers for the Apps env, replacing `uv pip compile`), `partition` (wheel vs sdist pins), `download` / `fetch-sdists` (fetch from the URLs + sha256 in `uv.lock` when no index is reachable), `split`, `check` (every pin has a wheel, every downloaded wheel's sha256 is in `uv.lock`, sdist-built wheels are pure Python, no file over the limit, no chunks for the MCP app). |
| `vendor_bootstrap.py` | Main app command. Reassembles chunks, installs `vendor/requirements.txt` with `--no-index --no-deps --target <tmp>/ontobricks-vendor/<lock>/site` (uv first, pip fallback), once per lock per container, then `exec`s `run.py` with that dir first on `PYTHONPATH`. |
| `requirements.txt` (root) | Installs nothing at Apps build time (chunked wheels cannot go through pip). |
| `src/mcp-server/requirements.txt` | `--no-index`, `--find-links ./vendor/wheels`, `-r vendor/requirements.txt` — installed by the Apps build, exactly like hello-abacus. |
| `app.yaml.template` / `src/mcp-server/app.yaml(.template)` | Commands no longer use `uv run`: `python vendor_bootstrap.py` and `python -c "from server.main import main; main()"`. |
| `databricks.yml` | `sync.include`: `vendor/**`, `src/mcp-server/vendor/**` (both gitignored). `sync.exclude`: `hello-abacus/`. |
| `Makefile` | `make artifact`, `make artifact-check`. |
| `scripts/deploy.sh` | Step 3b builds (or on `--dry-run` checks) the artifact before validate; the synced-source check now also probes `vendor_bootstrap.py` and both `vendor/requirements.txt`. |
| `.github/workflows/build-artifact.yml` | Builds + checks on GitHub-hosted runners; uploads `ontobricks-vendor-<sha>` (30-day retention). Triggers: manual, and push/PR touching either `uv.lock`, the build scripts, `vendor_bootstrap.py`, or the workflow. |

**Expected size (computed from `uv.lock`, not yet observed):**

| App | Packages | Wheel bytes | Wheels over 10 MB |
| --- | --- | --- | --- |
| Main (`ontobricks` + `lakebase` extra) | ~120 | ~211 MB | pyarrow 47.6, scipy 35.3, numpy 16.6, pandas 12.8, mlflow 12.0 MB |
| MCP (`mcp-ontobricks`) | ~75 | ~20 MB | none (largest under 9 MiB) |

Only `promise` is sdist-only in the main lock; it is built into a wheel by
`pip wheel` and must come out `py3-none-any`.

**Update 2026-11-17 — artifact delivered and verified in the workspace:**

* Uploaded to the UC volume above (main `vendor/`, `src/mcp-server/vendor/`;
  a separate `hello-abacus/app_artifact/` is unrelated to OntoBricks).
* `lock.sha256` equals the sha256 of the repo's `uv.lock` and
  `src/mcp-server/uv.lock` (same commit).
* `_vendor_artifact.py check`: main 120 pins, MCP 74 pins, all wheels present
  and matching `uv.lock`; largest file 9,437,184 bytes; no chunks for MCP.
* `vendor_bootstrap.reassemble` rebuilt 120 wheels in 5 s; all pass a zip
  integrity test.
* `uv pip install --no-index --no-deps --target … --python-version 3.11
  --python-platform x86_64-manylinux_2_28`: main 120 dists, 695 MB, 40 s on the
  cluster; MCP 74 dists, 78 MB, 11 s. A `--dry-run` with dependency resolution
  also succeeds for both, so each set is closed.
* Copied into the git folder; per-file sha256 identical to the volume. Both
  dirs are gitignored (git status unchanged).
* Not verified: importing the packages under Python 3.11 (no 3.11 on the
  cluster), and the real Apps start (I2–I5).
* The npm upload (`/Volumes/genie_agents/internal/npm/abacus-ontobricks-npm/`)
  is a pnpm store for `hello-abacus/frontend` only. OntoBricks has no
  `package.json` and needs no npm packages; `hello-abacus/` is excluded from
  the app sync.

**Originally, to unblock:**

1. Confirm the "Build offline wheel artifact" run on `feat/hello-abacus` is
   green (the workflow file push should have triggered it; not observed from
   the workspace). Or run `make artifact` on a laptop with `uv`.
2. Download `ontobricks-vendor-<sha>`, unzip at the root of a checkout of
   **the same commit**, `make artifact-check && make deploy`.

### B3 — `scripts/deploy.sh` cannot run inside the workspace

* The Databricks CLI on notebook compute refuses to run: "The Databricks CLI
  is only supported for interactive use from the web terminal."
* `deploy.sh` is a bash orchestrator around the CLI (render templates,
  resolve Lakebase, generate the instance target, validate, deploy, verify
  sync, bind, start, bootstrap permissions, init Lakebase schema). None of
  that can be executed from a notebook or by the assistant's sandbox.
* In an earlier session (2026-11-09), `apps deploy` from the assistant was
  blocked by guardrails; `bundle deploy` / `bundle run` via the assistant's
  CLI tool did work on 2026-11-16.

**Consequence:** the 2026-11-16 deploy was done by hand (see §3). For a
complete deploy, run `make deploy` from a laptop, CI, or the workspace web
terminal (untested: whether the web terminal has `uv`, Python 3.11 and the
checkout).

### B4 — Post-deploy bootstrap steps were skipped

The manual 2026-11-16 deploy ran only `bundle validate`, `bundle deploy` and
`bundle run ontobricks_dev_app`. `deploy.sh` does considerably more after
`bundle deploy`, and **none of it ran**:

| `deploy.sh` step | Skipped effect |
| --- | --- |
| Verify synced source (auto-heal stale sync snapshot) | No check that `run.py`, packages and now `vendor/` reached the workspace |
| Bind existing app | Not needed this time (state reused, see §3) |
| Start `ontobricks-abacus` / `mcp-ontobricks-abacus` | Only the main app was started; MCP never started |
| Verify deployment | No health probe |
| App self-permissions | App service principals may lack the grants they need on their own resources |
| Initialize Lakebase registry schema | `ontobricks_registry` schema/tables may not be initialized for this code version |
| Lakebase schema permissions | App SPs may lack schema grants → registry errors after boot |

**Read-only findings, 2026-11-17 (after both apps reached RUNNING):**

* Neither app SP (main `11092ec1-97af-4ca2-98a8-5d8e70f5bb00`, MCP
  `4dc39477-2954-450e-9929-2981dd9a3aba`) has any entry on: either app's ACL,
  job `306610647798839` (`[dev alex_baretto] ontobricks-abacus-graph-analytics`),
  the Lakebase project ACL, `genie_agents`, or `genie_agents.ontobricks`.
  The warehouse ACL is unreadable (deployer has CAN_USE, not Manage).
* Lakebase `ontobricks_registry`: the registry schema **does not exist**
  (only `public` and `__db_system`); no `pgcrypto`; both SP Postgres roles
  exist (created by the app resource binding); the deployer has CREATE on
  the database.
* Classic compute cannot reach the Lakebase endpoint (TCP timeout, same
  egress block as B1). Serverless can (private link, 192.168.200.30) and
  connects with the vendored pure `psycopg` wheel + the system `libpq`, so
  the Postgres half of the bootstrap is doable from a serverless notebook.
* Applying the grants from the assistant needs explicit, per-grant user
  authorization (blocked otherwise). Alternative for the schema: Initialize
  from the app's Settings → Registry page so the app SP owns it.

**Resolved 2026-11-17 (user-authorized, each item read back):**

| Step | Applied | Verified |
| --- | --- | --- |
| App ACLs | `ontobricks-abacus`: CAN_MANAGE → main SP, CAN_USE → MCP SP; `mcp-ontobricks-abacus`: CAN_MANAGE → MCP SP | ACL read back |
| Job `306610647798839` | CAN_MANAGE_RUN → both SPs | ACL read back |
| Lakebase project `ontobricks-abacus` | CAN_USE → both SPs | ACL read back |
| UC | `genie_agents`: USE_CATALOG, CREATE_SCHEMA; `genie_agents.ontobricks`: ALL_PRIVILEGES; both SPs | Grants read back |
| Registry initialize | App's `_init-lakebase-registry.py initialize` from serverless (Python 3.12; missing pure wheels from `vendor/` in `/tmp`, `databricks.sql` via namespace path). Schema owned by the deployer | 16 tables, 36 indexes, 3 sequences, 1 registry row; all 8 tables / 5 columns / 9 indexes of the lakebase-perms migration block present |
| pgcrypto | `CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public` | In `public` |
| Postgres grants | USAGE+CREATE on schema, DML on all tables, USAGE/SELECT/UPDATE on sequences, matching default privileges, for both SP roles | Both SPs: USAGE/CREATE true, DML on 16/16 tables, 3/3 sequences; default ACLs present |
| Warehouse CAN_USE | Skipped (deployer lacks Manage); assumed covered by the app's warehouse resource binding (not read back) | — |

Not replayed: `deploy.sh`'s `genie_agents.ontobricks_registry` UC schema
grant (that UC schema does not exist). Because the deployer owns the
registry schema, objects the app later creates are owned by the app SP;
future schema migrations should run as the table owner.

Once B1/B2 are past, an app that boots but was deployed without these steps
will most likely fail at the registry or permissions layer. **Deploy with
`make deploy`, not a bare `bundle deploy`.**

### B5 — Build logs are not readable from the assistant

* `databricks apps logs ontobricks-abacus --source BUILD` fails with
  "OAuth Token not supported for current auth type pat".
* The Apps API only returns the one-line summary ("Package installation
  failed with Databricks-managed Python constraints enabled. Check build logs
  for dependency conflicts or other installer errors.").
* So the exact failing package / network error of the 2026-11-13 and
  2026-11-16 builds was **inferred** from B1, not read. Open the app in the
  Apps UI → Logs to confirm. If the log shows a real dependency conflict
  rather than a network error, see I5.

---

## 3. How the 2026-11-16 deploy was done (and what it changed)

1. `scripts/deploy.config.sh` (instance `abacus`) and `databricks.yml` were
   already set: target `dev-lakebase-abacus`, warehouse `337986b7fa599984`,
   registry `genie_agents.ontobricks`, Lakebase project `ontobricks-abacus`,
   branch `production`, database `ontobricks_registry`.
2. Gitignored render outputs did not exist in this new git folder and were
   created by hand:
   * `app.yaml` — rendered from `app.yaml.template` with the config values
     plus `MCP_SP_CLIENT_ID=4dc39477-2954-450e-9929-2981dd9a3aba` (verified
     YAML-equal to a `string.Template` render of the template).
   * `resources/_generated_instance_target.yml` — the `dev-lakebase-abacus`
     target that `_ensure-instance-target.sh` would write.
3. `lakebase_database_resource_segment` defaults to the placeholder
   `db-unresolved-run-deploy-sh` in `databricks.yml`; it was passed as
   `--var=lakebase_database_resource_segment=db-1vo9-1qfyhj97g8` (the
   resolved id of `ontobricks_registry`). **Every** bundle command needs this
   var unless `deploy.sh` resolves it.
4. `bundle deploy -t dev-lakebase-abacus` → "Updated apps.mcp_ontobricks_app,
   apps.ontobricks_dev_app, jobs.graph_analytics_job".
5. `bundle run ontobricks_dev_app` → deployment `01f1e1fb41e2…` → FAILED (B1).

**Side effects to be aware of:**

* **Source-linked deployment.** Deploying a `mode: development` target from a
  workspace git folder enables source-linked deployment: both apps now point
  at `/Workspace/Users/alex.baretto@abacusinsights.com/abacus-ontobricks`
  directly instead of `~/.bundle/ontobricks-abacus/dev-lakebase-abacus/files`.
  Any edit in the git folder (including switching branches) is what the next
  app deployment runs. A laptop deploy will switch them back to the
  `.bundle/.../files` copy.
* **Shared Terraform state with the old repo.** The bundle state lives under
  `~/.bundle/ontobricks-abacus/dev-lakebase-abacus`, which the older git
  folder `~/ontobricks` (v0.9.1/v0.9.2, branch `fix/regind`) also deploys to.
  Deploying from both folders will overwrite each other's app config. Pick
  one folder and retire the other.
* A second state folder `~/.bundle/ontobricks-abacus/dev-lakebase` appeared
  (from validating the static `dev-lakebase` target). It holds no apps; it is
  safe to ignore, but do not deploy that target — it would try to create apps
  that already exist.

---

## 4. Environment facts the deploy depends on

| Resource | Value | Notes |
| --- | --- | --- |
| Workspace | `1654085560780927` (profile `demo-build`) | |
| Main app | `ontobricks-abacus`, SP `11092ec1-97af-4ca2-98a8-5d8e70f5bb00` | URL `https://ontobricks-abacus-1654085560780927.aws.databricksapps.com` |
| MCP app | `mcp-ontobricks-abacus`, SP `4dc39477-2954-450e-9929-2981dd9a3aba` | URL `https://mcp-ontobricks-abacus-1654085560780927.aws.databricksapps.com` |
| SQL warehouse | `337986b7fa599984` (`demo-genesis-warehouse`, serverless PRO Small, max 1 cluster) | Deployer has **CAN_USE only** — cannot change its config |
| Lakebase | project `ontobricks-abacus`, branch `production`, database `ontobricks_registry` (id `db-1vo9-1qfyhj97g8`) | Created via the Postgres (autoscaling) API |
| Registry / sync catalog | `genie_agents.ontobricks` / `genie_agents` | The deployer may only write to `genie_agents` (no grants elsewhere) |
| Apps runtime | Ubuntu 22.04, Python 3.11, uv 0.10.2 preinstalled | From Databricks Apps docs |

---

## 5. Unverified assumptions and risks in the offline-install design

Each of these can still fail the first real deploy. None could be tested
inside the workspace.

| # | Assumption | If wrong | How to check |
| --- | --- | --- | --- |
| I1 | Apps rejects individual app files over **10 MB**, so big wheels are split. (Not found in the docs; recalled.) | If there is no such limit, the splitting is just unnecessary complexity — no failure. If the limit is lower than 9 MiB, sync/deploy fails on chunks. | Deploy; or check Apps limits with Databricks support. |
| I2 | The first-start install of ~211 MB of wheels into `/tmp` finishes before Apps gives up on the app binding its port. | App marked unhealthy / restarted in a loop. | Watch `vendor_bootstrap:` lines and timing in the app logs. If too slow, move the big packages into the build-time install or trim dependencies. |
| I3 | `/tmp` in the Apps container has room for the unpacked set (~0.7 GB estimated) and survives the process exec. | `OSError: No space left` during install. | App logs; set `ONTOBRICKS_VENDOR_DIR` to another writable path. |
| I4 | Putting the vendored site dir **first on `PYTHONPATH`** makes the locked versions win over the Apps image's preinstalled ones (fastapi 0.115.0, databricks-sdk 0.33.0, mlflow-skinny 2.16.2, …). | Mixed versions → import errors or subtle bugs. | In the running app, log `fastapi.__version__`, `databricks.sdk.version`. |
| I5 | "Databricks-managed Python constraints" do not reject the MCP app's pinned set at build time (its versions differ from the preinstalled ones). | MCP build fails with a constraint conflict instead of a network error. | MCP build log. Fallback: give the MCP app the same runtime bootstrap as the main app. |
| I6 | `--target` installs work without `.pth` processing (site dirs on `PYTHONPATH` do not run `.pth` files). | A package relying on a `.pth` hook misbehaves. | Startup errors in logs; none expected in this lock. |
| I7 | pip honours `--find-links ./vendor/wheels` and the nested `-r vendor/requirements.txt` relative to the MCP app root at build time. | MCP build cannot find wheels. | MCP build log. |
| I8 | `pip download` with `manylinux_2_28` / `2_17` / `2014` + `cp311`/`abi3`/`none` tags finds a wheel for every pin, and those wheels load on Ubuntu 22.04 (glibc 2.35). | Build script fails ("No matching distribution"), or import fails at runtime. | First CI run. |
| I9 | Every downloaded wheel's sha256 appears in `uv.lock`. | `check` fails ("does not match any hash"). | First CI run. Fix with `uv lock --upgrade-package <pkg>`. |
| I10 | `promise` builds to a pure-Python wheel. | `check` fails ("built from an sdist but is not pure Python"). | First CI run. |
| I11 | The `pitfalls` extra stays out of the deployment (sentence-transformers pulls torch 502 MB + triton 188 MB). This matches the previous `uv run --extra lakebase` command. | Pitfalls features unavailable in the deployed app — same as before this change. | Product decision; vendoring torch is impractical. |
| I12 | The main app's files tree also carries `src/mcp-server/vendor/` (~20 MB), since both apps share one synced tree and `sync.exclude` cannot be per-app. | Only wasted space. | — |

---

## 6. Bugs found and fixed during this work

| # | Bug | Found by | Fix |
| --- | --- | --- | --- |
| F1 | `vendor_bootstrap.reassemble` symlinked whole wheels with a **relative** path, producing broken links when `vendor/` was given relatively (as `build_artifact.sh --check` does) → `FileNotFoundError` in `check`. | First offline test run | Symlink to `f.resolve()`. Re-tested: pass. |
| F2 | `TestStartCommandExtras` read `--extra lakebase` from the app command; the new command has none, so `test_lakebase_extra_is_still_requested` would fail in `ci.yml`. | Reading the tests | Test now reads extras from the main-app `build_one` line of `scripts/build_artifact.sh`; new `test_command_installs_offline_then_runs_the_app`. Verified it fails against the old `uv run` command. |
| F3 | `build_artifact.sh` used an empty bash array / `"$@"` under `set -u`, which errors on macOS's bash 3.2. | Review | `${check_flag:+"$check_flag"}` and `${1+"$@"}`. |
| F4 | `hello-abacus/` (a separate template project) was being synced into the app's files tree. | Review of sync rules | Added to `sync.exclude` and `.databricksignore`. |
| F5 | `scripts/deploy.sh` lost its executable bit on the way into the repo (mode 100755 → 100644). | Merge stat | `chmod +x` restored. |
| F6 | `DEPLOYMENT_BLOCKERS.md` at the repo root syncs into the app files tree (workspace IDs, SP ids). | This document's own §8 note | Added to `sync.exclude` and `.databricksignore`. |
| F7 | `make artifact` could not run anywhere without a `pypi.org` index — `uv pip compile` fetches the index even for fully-pinned input, and `pip download`/`pip wheel` need it too. A laptop whose egress allows `files.pythonhosted.org` but not `pypi.org` (same split seen on this Mac) could not build. | First laptop build attempt | `_vendor_artifact.py` gained `prune` (evaluates export markers for the fixed Apps env — offline replacement for `uv pip compile`), `download` and `fetch-sdists` (fetch by the URLs + sha256 already in `uv.lock`). `pip` remains the primary path; the lock-URL path is the fallback. Verified 2026-11-17: `make artifact` built 120 + 74 pins and `make artifact-check` passed on a machine with no `pypi.org` route. |

Earlier, already-fixed issues on the predecessor repo (`~/ontobricks`), for
context:

* `requirements.txt` with `-e ".[lakebase,pitfalls]"` forced a PEP 517
  isolated build fetching `hatchling` → DNS failure (2026-11-09). Replaced by
  `uv` + `--no-install-project`; then by this offline design.
* `--index-url https://pypi.org/simple` / `UV_DEFAULT_INDEX` overrides were
  tried and rejected (2026-11-10): pypi.org is not reachable either.

---

## 7. Test coverage gaps

The workspace cluster has no network and lacks `pydantic_settings` and
`pytest_asyncio`, so the repo's test setup (`conftest.py`) cannot load.

| What | Result |
| --- | --- |
| Offline test of split / check / bootstrap with fake wheels (in `/tmp`) | All cases passed: split into chunks; check pass; check fails on chunks with `--no-parts`, on a tampered chunk, on a missing pin; install via uv and via pip fallback; skip on restart; exec `run.py` with args; clear fatal error without `vendor/`. |
| `tests/units/settings/test_{bundle_job_resource,deploy_app_rename_guard,deploy_instance_id}.py`, `tests/units/config/test_no_registry_volume.py` (`--noconftest`) | 57 passed, 2 failed on the missing `pydantic_settings` import (not related to this change). |
| `tests/units/settings/test_app_yaml_template.py` (`Settings` import stubbed, round-trip tests deselected) | 14 passed, 6 deselected. |
| `tests/units/api/test_help_api.py`, MCP tests, full suite | **Not run.** Needs `ci.yml` (runs on PRs into master/main/develop) or a laptop with `uv run pytest`. |
| Real wheels, real Apps container (Python 3.11) | **Not run.** First real exercise is the CI build + first deploy. |

---

## 8. Git / review state

Commits pushed to `feat/hello-abacus` on 2026-11-16:

1. `build(deploy): vendor all runtime deps as wheels for offline Apps install` (14 files)
2. `ci: build the offline wheel artifact on GitHub-hosted runners` (2 files)
3. `test(settings): read requested extras from build_artifact.sh` (2 files)

Open items:

* **No pull request yet.** It cannot be opened from the workspace (no GitHub
  API access). Compare URL:
  `https://github.com/alexxx-db/ontobricks/compare/master...feat/hello-abacus?expand=1`
  (base assumed `master`; use `develop` if that is the integration branch).
* The branch also carries other work (e.g. the `hello-abacus/` folder); review
  "Files changed" before merging.
* `fix/regind` (in the old `~/ontobricks` folder) holds earlier deployment
  fixes; reconcile it with `feat/hello-abacus` so one branch is the source of
  truth.
* The rendered `app.yaml` and `resources/_generated_instance_target.yml` in
  this folder are gitignored and hand-made; `deploy.sh` regenerates both.
* This file itself lives at the repo root, which is synced into the app; add
  it to `sync.exclude` if that matters.

---

## 9. Path to a working deployment

1. **Decide on B1** with the network/platform owner: intentional block (keep
   the offline artifact) or a reachable mirror (simpler `--index-url`).
2. **Build the wheels** (B2): confirm the "Build offline wheel artifact" run is
   green, or run `make artifact` on a laptop. If it fails, the likely steps
   and fixes are in §5 (I8–I10).
3. **Deploy from outside the workspace** (B3/B4): on the same commit, with the
   artifact unzipped at the repo root, run `make artifact-check && make deploy`
   (it renders templates, resolves the Lakebase segment, deploys, verifies the
   sync, starts both apps, and runs the permission and Lakebase bootstrap).
4. **Watch the first start** (I2–I5): Apps UI → `ontobricks-abacus` → Logs.
   Expect `vendor_bootstrap: installing N vendored wheels offline…` then
   `installed in Ns`, then normal OntoBricks startup. For
   `mcp-ontobricks-abacus`, the build log should show an install from
   `./vendor/wheels` with no index.
5. **Retire the duplicate deploy source**: stop deploying `~/ontobricks` to the
   same bundle state.
6. **Open the PR** and let `ci.yml` run the full test suite (T1).
