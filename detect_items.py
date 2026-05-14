"""
detect_items.py — Item Discovery & Manifest Validation

Works for both Azure DevOps (ADO) and GitHub Actions (GHA).
Reads deploy_manifest.yml + workspace-src/ to resolve which items to deploy.

Outputs:
  - ADO:  ##vso[task.setvariable variable=DEPLOY_ITEMS]...
  - GHA:  writes to $GITHUB_OUTPUT
"""

import os
import sys
from pathlib import Path
import yaml

REPO_ROOT     = Path(__file__).resolve().parent
WORKSPACE_SRC = REPO_ROOT / "workspace-src"
MANIFEST_FILE = REPO_ROOT / "deploy_manifest.yml"

# Item types auto-created by Fabric — never deploy manually
AUTO_CREATED = {"SQLAnalyticsEndpoint"}

# Detect CI environment
IS_GHA = os.getenv("GITHUB_ACTIONS") == "true"
IS_ADO = os.getenv("TF_BUILD") == "True"


def load_manifest() -> dict:
    if not MANIFEST_FILE.exists():
        print("[WARN] deploy_manifest.yml not found — operating without manifest.")
        return {}
    with open(MANIFEST_FILE) as f:
        data = yaml.safe_load(f)
    return {item["name"]: item for item in data.get("items", [])}


def discover_items_in_repo(workspace_src: Path) -> dict:
    """Returns {item_name: item_type} for all folders in workspace-src/"""
    items = {}
    if not workspace_src.exists():
        return items
    for entry in sorted(workspace_src.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        parts = entry.name.rsplit(".", 1)
        if len(parts) == 2:
            item_name, item_type = parts
            items[item_name] = item_type
    return items


def resolve_deploy_names(requested, manifest, repo_items):
    warnings = []
    valid    = []

    if not requested or requested == ["all"]:
        candidates = [name for name, entry in manifest.items() if entry.get("enabled", True)]
    else:
        candidates = requested

    for name in candidates:
        if name not in repo_items:
            warnings.append(f"'{name}' not found in workspace-src/ — not Git-synced yet.")
            continue
        if repo_items[name] in AUTO_CREATED:
            warnings.append(f"'{name}' is {repo_items[name]} (auto-created by Fabric) — skipping.")
            continue
        if name in manifest and not manifest[name].get("enabled", True):
            warnings.append(f"'{name}' is disabled in manifest but explicitly requested — deploying anyway.")
        valid.append(name)

    return valid, warnings


def emit_output(deploy_items_str: str):
    """Emit output variable for ADO or GitHub Actions."""
    if IS_GHA:
        gh_output = os.getenv("GITHUB_OUTPUT", "")
        if gh_output:
            with open(gh_output, "a") as f:
                f.write(f"deploy_items={deploy_items_str}\n")
        print(f"[GHA] deploy_items={deploy_items_str}")
    else:
        # ADO output variable
        print(f"##vso[task.setvariable variable=DEPLOY_ITEMS]{deploy_items_str}")


def main():
    item_names_env = os.getenv("ITEM_NAMES", "all").strip()

    requested = (
        [n.strip() for n in item_names_env.split(",") if n.strip()]
        if item_names_env.lower() != "all"
        else ["all"]
    )

    print("=" * 65)
    print("  fabric-cicd — Item Discovery & Validation")
    print("=" * 65)

    manifest   = load_manifest()
    repo_items = discover_items_in_repo(WORKSPACE_SRC)

    print("\n📋 Manifest vs Repo Status:")
    print(f"  {'ITEM NAME':<35} {'TYPE':<20} {'MANIFEST':<12} {'IN REPO':<10} {'ENABLED'}")
    print(f"  {'-'*35} {'-'*20} {'-'*12} {'-'*10} {'-'*8}")

    all_known = sorted(set(list(manifest.keys()) + list(repo_items.keys())))
    for name in all_known:
        m_entry  = manifest.get(name, {})
        m_type   = m_entry.get("type", repo_items.get(name, "?"))
        in_mfst  = "✅ yes" if name in manifest else "➕ new"
        in_repo  = "✅ yes" if name in repo_items else "❌ no"
        enabled  = "✅" if m_entry.get("enabled", True) else "⛔ disabled"
        auto_tag = "  [auto]" if m_type in AUTO_CREATED else ""
        print(f"  {name:<35} {m_type:<20} {in_mfst:<12} {in_repo:<10} {enabled}{auto_tag}")

    if not repo_items:
        print("\n  [WARN] workspace-src/ is empty — connect source workspace to Git first.")
        emit_output("")
        return

    print(f"\n⚙️  Requested ITEM_NAMES: {item_names_env}")

    final_names, warnings = resolve_deploy_names(requested, manifest, repo_items)

    for w in warnings:
        print(f"  ⚠️  {w}")
        if IS_ADO:
            print(f"##vso[task.logissue type=warning]{w}")

    print("\n" + "=" * 65)
    if final_names:
        item_types = list(dict.fromkeys(repo_items[n] for n in final_names if n in repo_items))
        print(f"  ✅ Items to deploy  : {', '.join(final_names)}")
        print(f"     Item types       : {', '.join(item_types)}")
        print(f"     Note: fabric-cicd will compare with target workspace")
        print(f"           and skip any items already up-to-date.")
    else:
        print("  ⚠️  No items to deploy — check item names and workspace-src/ contents.")
    print("=" * 65)

    for name in final_names:
        entry = manifest.get(name, {})
        for dep in entry.get("depends_on", []):
            if dep not in final_names:
                print(f"  ⚠️  '{name}' depends on '{dep}' — ensure it exists in target workspace.")

    deploy_items_str = ",".join(final_names)
    emit_output(deploy_items_str)

    if not final_names:
        if IS_ADO:
            print("##vso[task.logissue type=warning]No items to deploy — deploy stage will be skipped.")
        sys.exit(1)


if __name__ == "__main__":
    main()
