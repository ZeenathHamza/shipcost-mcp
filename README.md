# ShipCost MCP

An open-source Model Context Protocol (MCP) server that gives AI agents illustrative freight estimates in Sri Lankan rupees (LKR), carrier comparisons, and multi-stop route planning across Sri Lanka.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)

## What it does

ShipCost MCP exposes simple logistics tools over MCP. It estimates freight charges and transit time across road, air, and sea modes, compares carrier options, and arranges pickup cities with a nearest-neighbor route heuristic. It is designed as a small, self-contained starting point for connecting AI agents to supply-chain workflows.

**Rates and distances are fictional, illustrative planning data, not live quotes or authoritative road measurements.** Replace them with verified Sri Lankan carrier APIs and operational routing data before using estimates in production decisions.

## Tools exposed

| Name | Description | Example input | Example output |
|---|---|---|---|
| `estimate_freight` | Estimates cost in LKR, transit time, and a suggested carrier. Modes: `FTL`, `LTL`, `AIR`, `SEA`. | `{"origin":"Colombo","destination":"Kandy","weight_kg":500,"distance_km":115,"mode":"FTL"}` | `{"origin":"Colombo","destination":"Kandy","mode":"FTL","estimated_cost_lkr":21000.0,"estimated_transit_days":1,"carrier_suggestion":"Lanka Road Freight"}` |
| `compare_carriers` | Ranks four illustrative mode/carrier options by estimated LKR cost. | `{"origin":"Colombo","destination":"Kandy","weight_kg":100,"distance_km":115}` | `[{"name":"Island Parcel Logistics","mode":"LTL","cost_lkr":6150.0,"transit_days":1},{"name":"Lanka Road Freight","mode":"FTL","cost_lkr":19800.0,"transit_days":1},{"name":"Colombo Coastal Freight","mode":"SEA","cost_lkr":29675.0,"transit_days":1},{"name":"Ceylon Air Cargo","mode":"AIR","cost_lkr":40700.0,"transit_days":1}]` |
| `calculate_route` | Orders supported pickup cities from a depot using a nearest-neighbor heuristic; the route does not return to the depot. | `{"depot":"Colombo","pickup_points":["Kandy","Galle","Matara"]}` | `{"optimized_order":["Kandy","Galle","Matara"],"total_distance_km":380,"estimated_time_hours":9.5}` |

`estimate_freight` and `compare_carriers` require positive, finite weight and distance values. The route tool accepts these Sri Lankan cities: Colombo, Kandy, Galle, Jaffna, Trincomalee, Batticaloa, Anuradhapura, Negombo, Matara, and Kurunegala.

## Quick start

Requires Python 3.11 or later.

### Local run

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

By default, the server uses streamable HTTP on `http://localhost:8080/mcp` and serves `http://localhost:8080/health`. Set `PORT` to change the listening port. For an MCP client that launches a local stdio process, configure its command as `python` with arguments `["server.py", "--transport", "stdio"]`.

### Docker

```bash
docker build -t shipcost-mcp .
docker run --rm -p 8080:8080 -e PORT=8080 shipcost-mcp
```

### Deploy to Cloud Run

```bash
gcloud run deploy shipcost-mcp --source . --region us-central1 --allow-unauthenticated
```

Cloud Run supplies `PORT`; the container binds to `0.0.0.0` and includes an HTTP health endpoint at `/health`.

## Example agent usage

An MCP client first initializes its connection and negotiates the protocol version, then sends a tool call over the streamable HTTP endpoint. Example `tools/call` request:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "estimate_freight",
    "arguments": {
      "origin": "Colombo",
      "destination": "Kandy",
      "weight_kg": 500,
      "distance_km": 115,
      "mode": "FTL"
    }
  }
}
```

Representative JSON-RPC response (the values are computed from the illustrative rates):

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"origin\":\"Colombo\",\"destination\":\"Kandy\",\"mode\":\"FTL\",\"estimated_cost_lkr\":21000.0,\"estimated_transit_days\":1,\"carrier_suggestion\":\"Lanka Road Freight\"}"
      }
    ],
    "isError": false
  }
}
```

## Security & secrets

- The core tools require no secrets. Freight estimates use fictional LKR pricing and are configured with Sri Lankan examples.
- Never commit `.env`; commit `.env.example` instead. Keep API keys and credentials in environment variables or a managed secret store, never in source code or container images.
- If extending the project with real carrier APIs, store credentials in Google Secret Manager and attach them to Cloud Run at deployment, for example:

  ```bash
  gcloud run deploy shipcost-mcp --source . --set-secrets=FEDEX_API_KEY=fedex-key:latest
  ```

- If a secret is ever committed, rotate it immediately with the provider, then clean repository history with `git filter-repo` or BFG. Removing a secret from the latest commit alone is not sufficient.
- Enable GitHub Secret Scanning (available for public repositories) and push protection where available.
- For vulnerability reports, see [SECURITY.md](SECURITY.md). Do not report security issues in public issues.

## Submit to Chainkit

Submit **ShipCost MCP** to the Chainkit supply chain AI directory under the category **Logistics**.

## License

MIT. See [LICENSE](LICENSE).
