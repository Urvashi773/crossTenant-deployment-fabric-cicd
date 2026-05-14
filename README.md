# Microsoft Fabric Cross-Tenant CI/CD — GitHub Actions

Deploy Microsoft Fabric item **schemas** across tenants using GitHub Actions. No data backup/restore — schema/metadata only.

## Two Pipelines

| Workflow | File | Approach |
|---|---|---|
| 🚀 Python Library | `deploy-fabric-python.yml` | `fabric-cicd` Python library (same as ADO) |
| 🚀 fab CLI | `deploy-fabric-cli.yml` | Official Microsoft `fab` CLI |

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
2. Select either **"Deploy Fabric Schema (Python Library)"** or **"Deploy Fabric Schema (fab CLI)"**.
3. Click **Run workflow** and fill in:
   - **Environment**: `PROD` / `UAT` / `DEV`
   - **Items to deploy**: e.g. `devsecops_lakehouse` or `all`
4. Click **Run workflow**.

---

## Difference Between the Two Approaches

**Python Library** (`deploy-fabric-python.yml`)
- Uses `fabric-cicd` Python package (`pip install fabric-cicd`)
- Compares source vs target item definitions — only deploys what changed
- Fine-grained item filtering via `deploy_manifest.yml`
- Best for: automated schema-diff-aware deployments

**fab CLI** (`deploy-fabric-cli.yml`)
- Uses the official Microsoft Fabric CLI (`pip install fabric-cli`)
- Deploys each item folder directly using `fab item deploy`
- Best for: simple, direct deployments matching `fab` CLI conventions