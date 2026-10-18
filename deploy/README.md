# Argus single-host deployment

This stack runs the production Next.js UI, Python API, PostgreSQL, FalkorDB and Caddy on one Linux host. PostgreSQL and FalkorDB are only reachable inside the Docker network. Caddy serves HTTPS after the configured DNS name points to the host.

## Host requirements

- Ubuntu 24.04 or another supported Linux distribution with Docker Engine and the Compose plugin
- 8 GiB RAM and at least 80 GiB persistent disk for graph browsing; use 16 GiB if uploads and CPU GLiNER/RelEx processing will run on this host
- Inbound TCP 80 and 443 for Caddy, and SSH restricted to your own IP
- A DNS A record for the selected hostname pointing to the host's public IP

These are starting requirements, not a benchmark promise. The app stores model downloads in the persistent app-data volume. The first upload can still wait for GLiNER/RelEx weights to download and load.

## First start

1. Check out the `ingestion-main` branch on the host.
2. Copy `deploy/argus.env.example` to `.env.production` in the repository root, restrict it to the deployment user (`chmod 600 .env.production`), and set the hostname, a generated Postgres password, and the existing Azure LLM2 and embedding deployment settings. Never commit `.env.production`.
3. Point DNS at the host and allow inbound 80/443.
4. Build and start the stack:

   ```sh
   docker compose --env-file .env.production -f deploy/compose.yaml up -d --build
   ```

5. Check status and startup logs:

   ```sh
   docker compose --env-file .env.production -f deploy/compose.yaml ps
   docker compose --env-file .env.production -f deploy/compose.yaml logs --tail=100 backend caddy
   ```

6. Open `https://<ARGUS_HOSTNAME>` after Caddy reports a certificate and the backend health check passes.

The app has no authentication, by design. Anyone who reaches the URL can use its workspaces and upload path. Keep this deployment on a private/unlisted demo URL until an access-control layer is explicitly requested.

## Runtime profile

The backend container uses the pinned CPU-only PyTorch wheel and starts two ingestion workers by default. It does not require a GPU. Set `ARGUS_LOCAL_MODEL_DEVICE=cpu`; do not raise worker concurrency on an 8 GiB host without measuring peak memory. Graph browsing and Azure-backed chat do not require local model inference. `HF_HOME` points into persistent app data so model weights survive container replacement.

The current deployment file creates empty database volumes. It does not export or import the local workstation's Postgres/FalkorDB volumes. Select and migrate only the intended demo workspace before the URL is shared; a whole-database dump could include unrelated projects and chat history.

## Maintenance

The named volumes `argus-postgres`, `argus-falkordb`, `argus-data`, `argus-caddy-data` and `argus-caddy-config` hold persistent data. Do not run `docker compose down -v` on the deployed host. Back up Postgres, FalkorDB persistence and `/app/data` before upgrades. Pin image changes deliberately and verify the workspace after each upgrade.
