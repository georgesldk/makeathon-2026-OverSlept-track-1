# Deploying EthnoTrace

This setup uses the existing `Makeathon_UI/` application: Vercel serves the Vite frontend and Render runs `server.py`. The scientific pipeline remains in its existing folders. No deployment, database provisioning or data import happens automatically from these files.

## Prerequisites

- A Neo4j database reachable from Render, already populated with a compatible, completed structured snapshot and its datasets. `127.0.0.1` on Render refers to the Render container, not your laptop. Use a network-accessible Neo4j service, encrypted transport where supported, and a read-only Neo4j account.
- A Git repository containing the UI files, including `Makeathon_UI/data/candidate_images.json` and `Makeathon_UI/public/atlas/`. Raw pipeline caches and credentials are not needed by the API and should not be committed.
- The review feature is a demonstration: examples are generated and clearly labelled, and submissions are disabled. They are not expert validation.

## 1. Render backend

Create a Python web service from the repository or use the root [`render.yaml`](render.yaml) Blueprint. For a manual service, use:

| Setting | Value |
| --- | --- |
| Root directory | `Makeathon_UI` |
| Build command | `pip install -r requirements.txt` |
| Start command | `python -B server.py` |
| Health check | `/api/health` |

Set these in Render's environment settings, not in Git:

| Variable | Meaning |
| --- | --- |
| `NEO4J_URI` | Reachable Bolt URI, for example an encrypted `neo4j+s://…` URI for a compatible provider. |
| `NEO4J_USER` / `NEO4J_PASSWORD` | Credentials for the read-only Neo4j account. |
| `NEO4J_DATABASE` | Name of the populated database on that service; it may differ from the local name. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact frontend origins, for example `https://your-project.vercel.app`. Include no paths or wildcard; add custom domains or specific preview origins separately. |
| `ETHNOTRACE_SNAPSHOT` | Optional: snapshot ID to select explicitly when more than one completed build exists. |

Render supplies `PORT`; the API binds to `0.0.0.0` when it is present. Locally it still defaults to `127.0.0.1:8787`; `API_HOST` and `API_PORT` can override the local defaults. The health endpoint checks both snapshot selection and a live Neo4j query.

**Review examples:** The API generates demo reviews in memory for the current snapshot. It does not accept or persist submissions.

## 2. Vercel frontend

Create a Vercel project pointing at this repository and set its root directory to `Makeathon_UI`. The included [`vercel.json`](Makeathon_UI/vercel.json) uses Vite, `npm ci`, `npm run build`, and `dist` as the output. Use a Node version supported by the project's `engines` field.

Set the following **build-time** environment variable in Vercel:

```text
VITE_API_BASE_URL=https://your-render-service.onrender.com
```

Use the Render origin without `/api` or a trailing path. This URL is public and is embedded in the frontend bundle; never put Neo4j credentials or other secrets in `VITE_` variables. Redeploy the frontend after changing it. Add the resulting Vercel origin to Render's `CORS_ALLOWED_ORIGINS` and redeploy/restart the backend after changing its environment. For Vercel preview deployments, add each specific preview origin you intend to allow.

For local development, leave `VITE_API_BASE_URL` unset. The frontend continues to use Vite's `/api` proxy to `127.0.0.1:8787`; the normal local instructions are in [Makeathon_UI/README.md](Makeathon_UI/README.md).

## 3. Verify without changing scientific data

After both services are running:

1. Request `https://your-render-service.onrender.com/api/health`; it should return `status: ok` and the intended snapshot ID.
2. Open the Vercel site and check that the catalogue loads entries for each book, historical passages and claims, candidate evidence, studies and the knowledge map. Check an Atlas entry and its image attribution when an image is available.
3. In browser developer tools, check that API requests reach the configured Render origin without CORS errors. Verify configured preview and custom domains individually.
4. Check that review examples are labelled as demonstrations and that the API rejects review submissions.

`test_deployment.py` checks CORS, demo-only reviews and database-health failure handling using a temporary local HTTP server and mocked database calls. Existing local integration tests use read-only database queries. Hosted verification must be performed after deployment; these files alone cannot verify remote credentials, networking, database contents or service availability.

Platform references: [Render web services](https://render.com/docs/web-services), [Render persistent disks](https://render.com/docs/disks), [Vite environment variables](https://vite.dev/guide/env-and-mode), and [Vercel project configuration](https://vercel.com/docs/project-configuration/vercel-json).
