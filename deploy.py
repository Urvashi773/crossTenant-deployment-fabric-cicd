"""
fabric-cicd Deployment Script — Name-Level Item Filtering
POC: devsecops_lakehouse (Lakehouse) + Hiawatha_DataAgent (DataAgent)
SPN Auth via ClientSecretCredential (yash-spn-DevOps-FabricAIUsecase)

HOW ITEM SELECTION WORKS:
  1. ITEM_NAMES env var controls which items deploy (by name, not just type).
     - "all"   → deploy all enabled items in deploy_manifest.yml
     - "devsecops_lakehouse"                    → Lakehouse only
     - "devsecops_lakehouse,Hiawatha_DataAgent" → both
  2. Selected item folders are copied into a temp staging directory.
     FabricWorkspace runs against the staging dir — so fabric-cicd only
     sees the items you selected (not the full workspace-src/).
  3. parameter.yml is copied into the staging dir too, so remapping works.
  4. Staging dir is cleaned up after deploy (success or failure).

Usage (PowerShell local):
    $env:AZURE_TENANT_ID     = "<tenant-id>"
    $env:AZURE_CLIENT_ID     = "89d5c54b-d273-464a-9d25-c10ef2352088"
    $env:AZURE_CLIENT_SECRET = "<secret>"
    $env:TARGET_WORKSPACE_ID = "<target-workspace-guid>"
    $env:DEPLOY_ENVIRONMENT  = "PROD"
    $env:ITEM_NAMES          = "devsecops_lakehouse"   # or "all"
    python deploy.py

Usage (ADO pipeline):
    All env vars injected by pipeline. ITEM_NAMES built by detect_items.py
    from the user's checkbox/text input and git change detection.
"""

import sys
import os
import shutil
import tempfile
from pathlib import Path
import yaml
from azure.identity import ClientSecretCredential
from fabric_cicd import FabricWorkspace, publish_all_items, unpublish_all_orphan_items

# ──────────────────────────────────────────────────────────
# Unbuffered output for ADO pipeline log streaming
# ──────────────────────────────────────────────────────────
sys.stdout.reconfigure(line_buffering=True, write_through=True)
sys.stderr.reconfigure(line_buffering=True, write_through=True)

# ──────────────────────────────────────────────────────────
# Optional DEBUG logging
# ──────────────────────────────────────────────────────────
try:
    from fabric_cicd import change_log_level
    if os.getenv("SYSTEM_DEBUG", "false").lower() == "true":
        change_log_level("DEBUG")
        print("[DEBUG] fabric-cicd debug logging enabled")
except ImportError:
    pass

# ──────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────
REPO_ROOT      = Path(__file__).resolve().parent
WORKSPACE_SRC  = REPO_ROOT / "workspace-src"
MANIFEST_FILE  = REPO_ROOT / "deploy_manifest.yml"
PARAMETER_FILE = REPO_ROOT / "parameter.yml"

# ──────────────────────────────────────────────────────────
# Read environment variables
# ──────────────────────────────────────────────────────────
tenant_id     = os.environ["AZURE_TENANT_ID"]
client_id     = os.environ["AZURE_CLIENT_ID"]
client_secret = os.environ["AZURE_CLIENT_SECRET"]
workspace_id  = os.environ["TARGET_WORKSPACE_ID"]
environment   = os.getenv("DEPLOY_ENVIRONMENT", "PROD")
item_names_env = os.getenv("ITEM_NAMES", "all").strip()   # "all" or "name1,name2"

print(f"[INFO] Target workspace ID : {workspace_id}")
print(f"[INFO] Environment         : {environment}")
print(f"[INFO] ITEM_NAMES input    : {item_names_env}")


# ──────────────────────────────────────────────────────────
# Load deploy_manifest.yml
# ──────────────────────────────────────────────────────────
def load_manifest() -> list[dict]:
    if not MANIFEST_FILE.exists():
        print("[WARN] deploy_manifest.yml not found — deploying all items in workspace-src/")
        return []
    with open(MANIFEST_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("items", [])


# ──────────────────────────────────────────────────────────
# Resolve item names to deploy
# Returns: (selected_names: list[str], item_types: list[str])
# ──────────────────────────────────────────────────────────
def resolve_items(item_names_env: str, manifest: list[dict]) -> tuple[list[str], list[str]]:
    manifest_by_name = {item["name"]: item for item in manifest}

    if item_names_env.lower() == "all":
        # Deploy all enabled items from manifest
        selected = [item for item in manifest if item.get("enabled", True)]
        print("[INFO] ITEM_NAMES=all → deploying all enabled manifest items")
    else:
        # Deploy specifically named items
        requested = [n.strip() for n in item_names_env.split(",") if n.strip()]
        selected = []
        for name in requested:
            if name in manifest_by_name:
                entry = manifest_by_name[name]
                if not entry.get("enabled", True):
                    print(f"[WARN] '{name}' is disabled in deploy_manifest.yml but was explicitly requested — deploying anyway.")
                selected.append(entry)
            else:
                print(f"[WARN] '{name}' not found in deploy_manifest.yml — will attempt to find it in workspace-src/ directly.")
                # Allow deploying items not in manifest yet (e.g., newly synced)
                selected.append({"name": name, "type": None, "enabled": True})

    item_names   = [item["name"] for item in selected]
    item_types   = list(dict.fromkeys(
        item["type"] for item in selected if item.get("type")
    ))  # unique types, preserving order

    return item_names, item_types


# ──────────────────────────────────────────────────────────
# Create staging directory with only selected item folders
# fabric-cicd scans repository_directory for item folders.
# By copying only selected folders here, we get name-level filtering.
# ──────────────────────────────────────────────────────────
def create_staging_dir(
    workspace_src: Path,
    selected_names: list[str],
    parameter_yml: Path,
) -> Path:
    staging = Path(tempfile.mkdtemp(prefix="fabric_deploy_"))
    print(f"[INFO] Created staging dir: {staging}")

    # Copy parameter.yml into staging dir (fabric-cicd looks for it in repository_directory)
    if parameter_yml.exists():
        shutil.copy2(parameter_yml, staging / "parameter.yml")
        print(f"[INFO] Copied parameter.yml → staging/parameter.yml")
    else:
        print("[WARN] parameter.yml not found — ID remapping will be skipped.")

    # Copy only selected item folders
    selected_set = set(selected_names)
    copied = []
    missing = []

    for folder in sorted(workspace_src.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        # Folder name format: ItemName.ItemType  (e.g., devsecops_lakehouse.Lakehouse)
        parts = folder.name.rsplit(".", 1)
        if len(parts) == 2:
            item_name = parts[0]
            if item_name in selected_set:
                dest = staging / folder.name
                shutil.copytree(folder, dest)
                copied.append(folder.name)
                selected_set.discard(item_name)

    # Report any selected names not found in workspace-src/
    for missing_name in selected_set:
        missing.append(missing_name)
        print(f"[ERROR] Item '{missing_name}' not found in workspace-src/ — it may not be Git-synced yet.")

    if missing:
        print(f"[ERROR] Missing items: {missing}")
        shutil.rmtree(staging, ignore_errors=True)
        sys.exit(1)

    print(f"[INFO] Staging dir contents ({len(copied)} items):")
    for name in copied:
        print(f"         • {name}")

    return staging


# ──────────────────────────────────────────────────────────
# Main deploy flow
# ──────────────────────────────────────────────────────────
manifest = load_manifest()
selected_names, item_types = resolve_items(item_names_env, manifest)

print(f"\n[INFO] Items to deploy    : {selected_names}")
print(f"[INFO] Item types in scope: {item_types}")

if not selected_names:
    print("[INFO] No items to deploy. Exiting.")
    sys.exit(0)

# Check dependencies declared in manifest
manifest_by_name = {item["name"]: item for item in manifest}
for name in selected_names:
    entry = manifest_by_name.get(name, {})
    for dep in entry.get("depends_on", []):
        if dep not in selected_names:
            print(f"[WARN] '{name}' depends on '{dep}' which is NOT in the selected items.")
            print(f"       Ensure '{dep}' already exists in the target workspace.")

# Create staging dir with only the selected item folders
staging_dir = None
try:
    staging_dir = create_staging_dir(
        workspace_src=WORKSPACE_SRC,
        selected_names=selected_names,
        parameter_yml=PARAMETER_FILE,
    )

    print(f"\n[INFO] Repository directory: {staging_dir}")

    # ──────────────────────────────────────────────────────
    # Authenticate via SPN
    # ──────────────────────────────────────────────────────
    token_credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )

    # ──────────────────────────────────────────────────────
    # Initialize FabricWorkspace against staging dir
    # item_type_in_scope derived from the selected items' types
    # ──────────────────────────────────────────────────────
    target_workspace = FabricWorkspace(
        workspace_id=workspace_id,
        environment=environment,
        repository_directory=str(staging_dir),
        item_type_in_scope=item_types,
        token_credential=token_credential,
    )

    # ──────────────────────────────────────────────────────
    # Deploy — with retry for Fabric async deprovisioning delay
    # When a Lakehouse is recently deleted, Fabric holds the name
    # for a few minutes. Retry up to 4 times (3 min total).
    # ──────────────────────────────────────────────────────
    import time
    MAX_RETRIES  = 4
    RETRY_DELAY  = 60   # seconds between retries

    print("\n[INFO] Publishing selected items...")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            publish_all_items(target_workspace)
            break   # success — exit retry loop
        except Exception as e:
            err_msg = str(e)
            if "not available yet" in err_msg and attempt < MAX_RETRIES:
                print(f"\n[WARN] Fabric item not ready yet (attempt {attempt}/{MAX_RETRIES}).")
                print(f"[WARN] Fabric is still deprovisioning the previously deleted item.")
                print(f"[INFO] Waiting {RETRY_DELAY}s before retry...")
                time.sleep(RETRY_DELAY)
                print(f"[INFO] Retrying publish (attempt {attempt + 1}/{MAX_RETRIES})...")
            else:
                raise   # re-raise if not a timing error or out of retries

    # NOTE: unpublish_all_orphan_items is intentionally NOT called here.
    # Running name-level selection means the staging dir only has a subset
    # of items — orphan removal would delete everything else in the target workspace.
    # Use full "all" deploys with orphan removal for cleanup runs.
    print("\n[INFO] Deployment complete.")
    print(f"[INFO] Deployed: {selected_names}")

finally:
    # Always clean up the staging directory
    if staging_dir and staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
        print(f"[INFO] Cleaned up staging dir: {staging_dir}")

