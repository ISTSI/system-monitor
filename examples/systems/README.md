# Two systems in one deployment

`alpha.project.json/.yaml` and `beta.project.json/.yaml` are complete schema-2.0 configurations. Each pair is equivalent. Project IDs/names differ; entity IDs, host/process names, source paths and addresses intentionally overlap to test correct scope. They contain documentation/example network addresses only; do not connect to production or assume target approval.

Create/import two named systems as Administrator, map credentials/trust only to authorized local test hosts, and open each `/systems/{project_id}/topology` in separate windows of the **same browser profile/account**. Workspaces are server-issued in the application; the `*.workspace.json` files are response examples, never handles to adopt on page open. One MariaDB/app/proxy deployment serves both. See AT91–AT120 for future application checks.
