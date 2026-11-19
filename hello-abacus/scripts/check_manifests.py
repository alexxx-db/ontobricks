"""Check every slice's feature.yaml against its code and the bundle.

Fails when a slice has no manifest or its name differs from its directory, when a
listed port has no module in ports/ or router() takes a port the manifest does not
list, or when the app resource's bindings and user API scopes differ from the union of
the manifests, in either direction.

Run from the bundle root: uv run --project backend python scripts/check_manifests.py
"""

import ast
import sys
from pathlib import Path

import yaml

PACKAGE = Path("backend/backend")
PORTS_MODULE = "backend.ports."


def router_ports(route: Path) -> set[str]:
    """The ports/ modules whose Protocols annotate router()'s parameters."""
    tree = ast.parse(route.read_text(), filename=str(route))
    protocols = {
        alias.asname or alias.name: node.module.removeprefix(PORTS_MODULE)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(PORTS_MODULE)
        for alias in node.names
    }
    routers = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "router"]
    if not routers:
        return set()
    params = routers[0].args.args + routers[0].args.kwonlyargs
    return {protocols[p.annotation.id] for p in params if isinstance(p.annotation, ast.Name) and p.annotation.id in protocols}


def app_resource() -> dict:
    """The one app declared under resources/."""
    apps = [
        app
        for path in sorted(Path("resources").glob("*.yml"))
        for app in ((yaml.safe_load(path.read_text()) or {}).get("resources", {}).get("apps") or {}).values()
    ]
    if len(apps) != 1:
        sys.exit(f"Expected one app under resources/, found {len(apps)}")
    return apps[0]


def main() -> int:
    errors: list[str] = []
    ports = {p.stem for p in (PACKAGE / "ports").glob("*.py") if p.stem != "__init__"}
    resources: set[str] = set()
    scopes: set[str] = set()

    for slice_dir in sorted(d for d in (PACKAGE / "features").iterdir() if d.is_dir() and d.name != "__pycache__"):
        manifest_path = slice_dir / "feature.yaml"
        if not manifest_path.exists():
            errors.append(f"{slice_dir}: no feature.yaml")
            continue
        manifest = yaml.safe_load(manifest_path.read_text()) or {}
        if manifest.get("name") != slice_dir.name:
            errors.append(f"{manifest_path}: name {manifest.get('name')!r} differs from directory {slice_dir.name!r}")
        listed = set(manifest.get("ports") or [])
        for port in sorted(listed - ports):
            errors.append(f"{manifest_path}: port {port!r} has no module in ports/")
        route = slice_dir / "route.py"
        for port in sorted(router_ports(route) - listed if route.exists() else set()):
            errors.append(f"{manifest_path}: router() takes port {port!r}, which the manifest does not list")
        resources |= set(manifest.get("resources") or [])
        scopes |= set(manifest.get("scopes") or [])

    app = app_resource()
    bound = {r["name"] for r in app.get("resources") or []}
    granted = set(app.get("user_api_scopes") or [])
    for name in sorted(resources - bound):
        errors.append(f"resource {name!r} is in a manifest but not bound to the app")
    for name in sorted(bound - resources):
        errors.append(f"resource {name!r} is bound to the app but no manifest lists it")
    for name in sorted(scopes - granted):
        errors.append(f"scope {name!r} is in a manifest but not in the app's user_api_scopes")
    for name in sorted(granted - scopes):
        errors.append(f"scope {name!r} is in the app's user_api_scopes but no manifest lists it")

    for error in errors:
        print(f"FAILED: {error}")
    if not errors:
        print("Manifests match the code and the bundle.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
