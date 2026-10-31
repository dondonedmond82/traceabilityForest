# Forest Timber Traceability Blockchain

A local proof-of-concept for timber identity and chain-of-custody tracking.

## Architecture
- Frontend: Python Panel
- Backend: JavaScript / Node.js / Express
- Ledger: persistent SHA-256 hash-linked blocks in `data/forest-blockchain.json`
- Integration boundary: REST API for an OpenForis Arena adapter

**Important:** this is a single-node development blockchain prototype. It provides tamper-evident hash linking and verification, but it is not a decentralized consensus network and does not by itself provide independent validators, distributed replication, or production-grade immutability.

## Requirements
- Node.js 18 or newer
- Python 3.10 or newer
- Windows PowerShell or Command Prompt

## Run on Windows
1. Extract the ZIP file.
2. Open Terminal in the project folder.
3. Start the backend in terminal 1:
   ```powershell
   npm install
   Copy-Item .env.example .env
   node .\blockchain.js
   ```
4. Start Panel in terminal 2:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   $env:BLOCKCHAIN_API_URL="http://127.0.0.1:3000/api/v1"
   $env:API_KEY="dev-change-this-key"
   panel serve .\app.py --address 127.0.0.1 --port 5006 --show --autoreload
   ```
5. Open `http://127.0.0.1:5006`.

Alternatively, double-click `start_backend.bat` and `start_panel.bat` in two separate terminals. The batch files use the development API key (`dev-change-this-key`). Change it consistently in `.env` and the Panel environment before any shared or production use.

## API endpoints
- `GET /api/v1/health` (health check; no key)
- `GET /api/v1/chain`
- `GET /api/v1/timber`
- `POST /api/v1/timber`
- `POST /api/v1/events`
- `GET /api/v1/timber/:grumeId/history`
- `GET /api/v1/ledger/verify`

Protected endpoints require header `x-api-key`.

## Example event payload
```json
{
  "grumeId": "RCA-LOB-2026-0001",
  "eventType": "TRANSPORT",
  "actor": "Transport Company ABC",
  "location": "Bangui",
  "notes": "Loaded for transport"
}
```

## OpenForis Arena integration
The backend exposes an API boundary. A real Arena integration requires the Arena instance URL, API authentication method, relevant data model/table names, and permission to call the Arena API. The current UI includes an integration configuration placeholder; it does not pretend to synchronize with Arena until that adapter is configured.

## Production hardening checklist
- Replace local JSON storage with PostgreSQL or another transactional database.
- Use authenticated users, role-based permissions, TLS, secret management and audit logging.
- Add distributed validators/consensus and independent node replication if a decentralized blockchain is required.
- Add signed transactions and key management.
- Add backups, monitoring, rate limits, schema validation and automated tests.
- Validate legal and operational requirements with the relevant forestry authority.
