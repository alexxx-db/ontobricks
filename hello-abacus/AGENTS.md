# AGENTS.md

hello-abacus is a Databricks App generated from the Hello Abacus Copier template. Hello Abacus is the approved way Abacus builds applications, and its docs are the rules for this code. This file points to them rather than copying them, because a copy drifts from its source.

Hello Abacus is https://gitlab.com/abacusinsights/abacusai/hello-abacus, read from its `develop` branch. If you cannot open the links below, clone it and read the same paths.

- Start with [getting-started.md](https://gitlab.com/abacusinsights/abacusai/hello-abacus/-/blob/develop/docs/starter/getting-started.md). Its Next table names the short reference for each task, and each links to the guide section that owns the detail.
- Anything no Hello Abacus ADR decides is open. Each ADR in [decisions/](https://gitlab.com/abacusinsights/abacusai/hello-abacus/-/tree/develop/docs/decisions) lists what it leaves open under "Not decided here". Do not infer an answer from this code, from another app, or from another repository. When a task needs one, leave that part unbuilt and raise it under a `## Not covered by Hello Abacus` heading in the merge request description.
- Conformance is what `bash scripts/check.sh` says. Run it before you push. CI runs it too.

This project's backend package is `backend`, at `backend/backend/`. Code paths in the Hello Abacus guides are relative to this project's root.
