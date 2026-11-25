# CodeAlpha_BusPassSystem

Cloud-hosted **bus pass booking** system for CodeAlpha Cloud Computing Task 3.

TransitCloud issues account-bound digital passes so a ticket cannot be lost with a paper slip or stolen as a transferable screenshot ID. Fares are taken from a server-side catalogue (the browser never chooses the price). Duplicate active passes on the same corridor are rejected. The app exposes `/api/health` so extra instances can be placed behind a load balancer when booking traffic rises.

## Run locally

```bash
cd CodeAlpha_BusPassSystem
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8001
```

Open http://127.0.0.1:8001

Demo accounts:

- Passenger: `passenger@nimbus.cloud` / `passenger123`
- Ops: `admin@nimbus.cloud` / `admin123`

## Scale-style deploy

```bash
docker compose up --build --scale app=2
```

Nginx fronts the replicas. For a public cloud, replace compose with AWS ECS/Fargate, Azure Container Apps, or Cloud Run and attach an autoscaling policy on CPU or request count.

## Requirements covered

- Online booking hosted as a container
- Loss/theft: wallet is in the cloud and passes are bound to the logged-in account
- Incorrect pricing: amount is never read from the client
- High traffic: health checks + replica-ready compose
- Seamless booking: unique `TC-XXXXXXXX` pass codes and a digital boarding view
