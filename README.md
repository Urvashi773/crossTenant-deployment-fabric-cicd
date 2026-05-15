# Microsoft Fabric Cross-Tenant CI/CD — GitHub Actions

Deploy Microsoft Fabric item **schemas** across tenants using GitHub Actions. No data backup/restore — schema/metadata only.

## Two Pipelines

| Workflow | File | Approach |
|---|---|---|
| 🚀 Python Library | `deploy-fabric-python.yml` | `fabric-cicd` Python library (same as ADO) |
| 🚀 REST API | `deploy-fabric-cli.yml` | Direct Fabric REST API via `curl` + Azure AD SPN token |

Both are triggered manually via **Actions → Run workflow**.

---

## Prerequisites

### 1. GitHub Secrets
Add these under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `TARGET_TENANT_ID` | Azure AD tenant of the target Fabric workspace |
| `TARGET_CLIENT_ID` | SPN App (client) ID — must be Workspace Admin on target |
| `TARGET_CLIENT_SECRET` | SPN client secret |
| `TARGET_WORKSPACE_ID` | GUID of the target Fabric workspace |

### 2. SPN Permissions
The SPN must have **Workspace Admin** or **Contributor** role on the target Fabric workspace.

### 3. Fabric Capacity
Target workspace must be on an active Fabric capacity (F SKU / P SKU / Trial).

---

## Configuration

### `deploy_manifest.yml`
Controls which items are deployable. Set `enabled: true` to include an item.

### `parameter.yml`
Handles cross-tenant GUID remapping (e.g. Lakehouse ID in source → Lakehouse ID in target).

### `workspace-src/`
Contains the Fabric item definitions (synced from source workspace via Fabric Git integration).

---

## How to Run

1. Go to **Actions** tab in this repository.
2. Select either workflow.
3. Click **Run workflow** and fill in:
   - **Environment**: `PROD` / `UAT` / `DEV`
   - **Items to deploy**: e.g. `devsecops_lakehouse` or `all`
4. Click **Run workflow**.

> ⚠️ **After deleting a Lakehouse:** Fabric takes 2–3 minutes to fully deprovision it. The Python Library pipeline automatically retries every 60s (up to 4 attempts) to handle this. The REST API pipeline will also need a short wait before re-running.

---

## 🤖 Enabling Data Agent Migration

The **Python Library pipeline** (`deploy-fabric-python.yml`) supports deploying `DataAgent` items.

### Step 1 — Enable in `deploy_manifest.yml`
```yaml
- name: Hiawatha_DataAgent
  type: DataAgent
  enabled: true        # ← Change from false to true
```

### Step 2 — Fill in Target Lakehouse ID in `parameter.yml`
The DataAgent definition JSON contains the **source Lakehouse GUID** which must be remapped to the target Lakehouse GUID:
```yaml
find_replace:
  - find_value: "9544494b-3bc6-44b6-8d8f-f65851debfb9"    # source LH ID
    item_type: "DataAgent"
    item_name: "Hiawatha_DataAgent"
    replace_value:
      PROD: "92b1222a-0427-4440-b59c-8d0856dde928"         # ← your target LH ID
```
> Find your target Lakehouse GUID: Fabric portal → Target workspace → `devsecops_lakehouse` → copy GUID from the URL.

### Step 3 — Sync `Hiawatha_DataAgent` to workspace-src/
The DataAgent definition must exist in `workspace-src/`. Connect the source workspace to this Git repository via **Fabric → workspace → Git integration → Sync**.

### Step 4 — Run with both items
```
Items to deploy: devsecops_lakehouse,Hiawatha_DataAgent
```
`fabric-cicd` respects the `depends_on` in the manifest — it deploys the Lakehouse first, then the DataAgent automatically.

### ⚠️ Requirement: Paid Fabric Capacity
DataAgent requires **F SKU, P SKU, or Trial Fabric capacity** on the target workspace. Without it, the Fabric API returns a capacity error and deployment will fail.

---

## ❌ Why the REST API Pipeline Cannot Deploy DataAgent

The REST API pipeline (`deploy-fabric-cli.yml`) uses direct Fabric REST API calls. While it works well for simple items like **Lakehouse** (which is just a shell with no definition payload), it has these limitations with DataAgent:

| Reason | Detail |
|---|---|
| **No provisioning wait logic** | DataAgent creation is async. `fabric-cicd` internally polls the Fabric API until provisioning completes. The REST API pipeline has no such polling logic. |
| **Complex definition handling** | DataAgent definitions contain embedded JSON with nested workspace references. `fabric-cicd` knows how to parse, remap, and re-encode these correctly. The REST API pipeline's generic base64 encoding may not handle all edge cases. |
| **Item-type-specific API** | DataAgent has its own provisioning endpoint and requirements. The REST API pipeline's `SIMPLE_ITEMS` routing only covers `Lakehouse` currently. |

**Bottom line:** For DataAgent, always use the **Python Library pipeline**. The REST API pipeline is best suited for simpler schema-only items (Lakehouses, Notebooks, DataPipelines) where definition upload is straightforward.

---

## Difference Between the Two Approaches

**Python Library** (`deploy-fabric-python.yml`)
- Uses `fabric-cicd` Python package
- Compares source vs target — only deploys what changed (smart diff)
- Handles complex item types: Lakehouse, DataAgent, Notebook, DataPipeline, etc.
- Built-in retry for Fabric timing issues
- Best for: full production deployments, DataAgent migration

**REST API** (`deploy-fabric-cli.yml`)
- Calls Fabric REST APIs directly (no third-party library)
- Uses `GET /items` to discover, `POST /lakehouses` or `POST /items` to create
- Lightweight, no pip dependencies beyond `pyyaml`
- Best for: simple items, debugging, understanding what APIs fabric-cicd calls internally