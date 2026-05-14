# workspace-src — Item Definitions from Source Workspace

This folder will be **auto-populated by Fabric Git Integration** when you connect the source workspace to this repo.

## How it gets populated

1. Go to Fabric portal → source workspace (devsecops / JD-JDDO-Finance-Resources-Dev)
2. **Workspace Settings → Git Integration**
3. Connect to this ADO repo:
   - Organization: `YashTech-DevOps`
   - Project: `YASH-DevOps-Training`
   - Repo: `multitenant-deployment-cicd-fabric`
   - Branch: `main`
   - **Git folder: `/workspace-src`**  ← important
4. Click **Connect and Sync**

After connection, Fabric will commit the following folders here:
```
workspace-src/
  devsecops_lakehouse.Lakehouse/
    .platform
  devsecops_lakehouse.SQLAnalyticsEndpoint/
    .platform   (auto-created, no action needed)
  Hiawatha_DataAgent.DataAgent/
    .platform
    DataAgentDefinition.json   ← contains Lakehouse ID reference to remap
```

## Creating the DataAgent

Before connecting to Git:
1. In source workspace → New item → **Data Agent**
2. Name it (e.g., `Hiawatha_DataAgent`)
3. Connect it to `devsecops_lakehouse`
4. Save → Git sync will pick it up

## After items appear here

Update `parameter.yml` at repo root:
- Replace `PLACEHOLDER_SOURCE_LAKEHOUSE_ID` with the Lakehouse ID from source workspace
- Replace `PLACEHOLDER_SOURCE_WORKSPACE_ID` with the source workspace ID
- Replace `PLACEHOLDER_TARGET_LAKEHOUSE_ID` with the target workspace Lakehouse ID (after first deploy)
