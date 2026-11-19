"""Apply Atlas versioned migrations to Lakebase as the job's run-as identity.

Arguments: the bundle's workspace file path, the Lakebase endpoint name, the database,
and the app's user group role. Run by `databricks bundle run migrate` after
`bundle deploy` and before the app starts.

The connection URL carries a credential, so it reaches Atlas through the environment,
never argv, and Atlas's output is scrubbed of it before printing.
"""

import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.parse

from databricks.sdk import WorkspaceClient

bundle_root, endpoint, database, app_users_role = sys.argv[1:5]

# Serverless has no internet egress, so the Atlas binary ships with the bundle.
# Workspace files are not executable, so it is copied out first.
arch = "arm64" if platform.machine() in ("aarch64", "arm64") else "amd64"
atlas = "/tmp/atlas"
shutil.copyfile(f"{bundle_root}/bin/atlas-linux-{arch}", atlas)
os.chmod(atlas, os.stat(atlas).st_mode | stat.S_IEXEC)

w = WorkspaceClient()
user = w.current_user.me().user_name
host = w.postgres.get_endpoint(name=endpoint).status.hosts.host
token = w.postgres.generate_database_credential(endpoint=endpoint).token
print(f"atlas {arch}: applying migrations to {host}/{database} as {user}, granting {app_users_role}")

q = lambda v: urllib.parse.quote(v, safe="")
env = {**os.environ, "ATLAS_URL": f"postgres://{q(user)}:{q(token)}@{host}:5432/{database}?sslmode=require"}
target = ["--config", "file://atlas.hcl", "--env", "lakebase", "--var", f"app_users_role={app_users_role}"]

# Every Lakebase database contains the system schema __db_system, so Atlas's
# clean-database check fails. It only runs before the first revision is recorded.
for command in (["version"], ["migrate", "apply", "--allow-dirty"], ["migrate", "status"]):
    args = [atlas, *command] + (target if command[0] == "migrate" else [])
    # atlas.hcl resolves the migrations directory against the working directory.
    result = subprocess.run(args, cwd=bundle_root, env=env, capture_output=True, text=True)
    output = (result.stdout + result.stderr).replace(token, "***").replace(q(token), "***")
    print(f"$ atlas {' '.join(command)}\n{output}")
    if result.returncode != 0:
        sys.exit(f"atlas {' '.join(command)} exited {result.returncode}")
