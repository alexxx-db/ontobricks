# hello-abacus

React + Vite frontend, FastAPI backend, and a bundle-managed Lakebase Postgres database deployed as one Databricks App.

## Structure

Vertical slices over typed ports, per Hello Abacus [slices-and-ports.md](https://gitlab.com/abacusinsights/abacusai/hello-abacus/-/blob/develop/docs/guides/slices-and-ports.md). Read it before adding a feature, a port, or a migration. [AGENTS.md](AGENTS.md) says where the rest of the rules are.

```
backend/backend/
  features/   one directory per slice, each with feature.yaml, route.py, test_route.py
  kernel/     pure types shared across the app
  ports/      Protocols only
  adapters/   the only code that imports a vendor SDK
  runtime/    the composition root: config, wiring, server
backend/tests/contracts/   one contract test per port
frontend/src/app/          the shell; composes slices
frontend/src/features/     each slice's UI, with the backend slice's name
migrations/                Atlas versioned migrations
jobs/migrate.py            applies them from a serverless job
```

## Checks

```bash
bash scripts/check.sh
```

It runs the backend tests, the import contracts, the manifest check, the frontend lint, tests and build, and `atlas migrate validate` if Atlas is installed. `.gitlab-ci.yml` runs the same script.

Laptops cannot reach Lakebase, so the app is not run locally against it. Route tests run against in-memory adapters, and the deployed `dev` target is where the real adapter is exercised.

## Local bundle deploy

The bundle creates a Lakebase Autoscaling project, production branch, app-owner role, database, and read-write compute endpoint, the `migrate` job, a Unity Catalog schema in `var.catalog`, and a SQL warehouse. The app is granted `CAN_CONNECT_AND_CREATE` on the generated database and the `postgres` user API scope.

The `dev` target isolates each developer with a user-specific workspace path and resource suffix; its Lakebase project is purged when destroyed. The `prd` target is a singleton with a shared production workspace path; destroying it soft-deletes its Lakebase project, which is purged with its data 7 days later.

The app name is the project name plus, in `dev`, `-` and your user name, and an app name is at most 30 characters. A longer name fails the deploy after the Lakebase resources are created.

Set the bundle's inputs for your workspace, once per shell. These are `abacus-dev`'s; `abacus-dev-reader` stands in for the client app group until it exists:

```bash
export BUNDLE_VAR_customer=abacus BUNDLE_VAR_workspace=dev BUNDLE_VAR_catalog=abacus_dev_catalog
export BUNDLE_VAR_app_viewers_group=abacus-dev-reader
```

Deploy with:

```bash
databricks bundle deploy -t dev --profile <PROFILE>
databricks bundle run migrate -t dev --profile <PROFILE>
databricks bundle run web -t dev --profile <PROFILE>
```

Stand it down with:

```bash
databricks bundle destroy -t dev --profile <PROFILE>
```

In `dev` this deletes the Lakebase project and its data, and the Unity Catalog schema with its tables.

In `dev`, `bundle deploy` runs `scripts/fetch_atlas.sh`, which downloads the pinned, checksummed Atlas binaries into `bin/`, because serverless has no internet egress. In `prd`, Seiji copies the binaries CI published with the tag instead.

The app runs no DDL. The `migrate` job applies `migrations/` with Atlas as the job's run-as identity and grants what each migration creates to the `app_users_role` group role.

The app connects to Lakebase as the signed-in user, never as its service principal. Each user needs their own Lakebase Postgres role, a member of `app_users_role`, or their requests fail. Creating one, and reading the errors, is Hello Abacus [migrations.md](https://gitlab.com/abacusinsights/abacusai/hello-abacus/-/blob/develop/docs/guides/migrations.md#a-second-user). State that holds PHI does not go in Lakebase yet; see the same guide's [PHI in Lakebase](https://gitlab.com/abacusinsights/abacusai/hello-abacus/-/blob/develop/docs/guides/migrations.md#phi-in-lakebase).

Backend dependencies are defined in `backend/pyproject.toml` and locked in `backend/uv.lock`. `bundle deploy` builds `app_artifact/`, which vendors them as wheels so the app installs with no package index; `bash scripts/check.sh artifact` proves it does.

## Deploying beyond `dev`

Seiji deploys the `prd` target with the artifact CI publishes for each tag, through `seiji-packaging.yaml` and the hooks in `deploy/`; see Hello Abacus [Deploying through Seiji](https://gitlab.com/abacusinsights/abacusai/hello-abacus/-/blob/develop/docs/guides/deploy.md#deploying-through-seiji). `bash scripts/check.sh deploy` tests the hooks. The bundle grants the app, its SQL warehouse and its Unity Catalog schema to the groups `databricks.yml` names from the customer and workspace; see Hello Abacus [Grants](https://gitlab.com/abacusinsights/abacusai/hello-abacus/-/blob/develop/docs/guides/asset-bundles.md#grants).
