require("dotenv").config();
const express = require("express");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const app = express();
app.use(express.json({ limit: "1mb" }));
const PORT = Number(process.env.PORT || 3000);
const API_KEY = process.env.API_KEY || "dev-change-this-key";
const DATA_DIR = path.join(__dirname, "data");
const LEDGER_FILE = path.join(DATA_DIR, "forest-blockchain.json");
fs.mkdirSync(DATA_DIR, { recursive: true });

const sha256 = value => crypto.createHash("sha256").update(value).digest("hex");
const now = () => new Date().toISOString();
function readLedger() {
  if (!fs.existsSync(LEDGER_FILE)) {
    const genesis = createBlock(0, [], "0".repeat(64));
    const initial = { chain: [genesis], pendingTransactions: [], timber: {} };
    writeLedger(initial);
    return initial;
  }
  return JSON.parse(fs.readFileSync(LEDGER_FILE, "utf8"));
}
function writeLedger(data) {
  const tmp = LEDGER_FILE + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2));
  fs.renameSync(tmp, LEDGER_FILE);
}
function blockHash(block) {
  return sha256(JSON.stringify({
    index: block.index, timestamp: block.timestamp,
    transactions: block.transactions, previousHash: block.previousHash, nonce: block.nonce
  }));
}
function createBlock(index, transactions, previousHash) {
  const block = { index, timestamp: now(), transactions, previousHash, nonce: 0 };
  block.hash = blockHash(block);
  return block;
}
function auth(req, res, next) {
  if (process.env.NODE_ENV === "production" && !process.env.API_KEY) {
    return res.status(500).json({ error: "API_KEY must be configured in production" });
  }
  const supplied = req.get("x-api-key");
  if (!supplied || supplied !== API_KEY) return res.status(401).json({ error: "Invalid or missing API key" });
  next();
}
app.get("/api/v1/health", (_req, res) => res.json({
  service: "Forest Traceability Blockchain API", version: "1.0.0", status: "ok", timestamp: now()
}));
app.use("/api/v1", auth);

app.get("/api/v1/chain", (_req, res) => {
  const ledger = readLedger();
  res.json({ chain: ledger.chain, pendingTransactions: ledger.pendingTransactions.length });
});
app.get("/api/v1/timber", (_req, res) => {
  const ledger = readLedger();
  res.json({ timber: Object.values(ledger.timber) });
});
app.post("/api/v1/timber", (req, res) => {
  const { grumeId, species, volumeM3, diameterCm, lengthM, harvestDate, origin, gps } = req.body || {};
  if (!grumeId || !species || !Number.isFinite(Number(volumeM3)) || Number(volumeM3) <= 0)
    return res.status(400).json({ error: "grumeId, species and positive volumeM3 are required" });
  const ledger = readLedger();
  if (ledger.timber[grumeId]) return res.status(409).json({ error: "This grumeId is already registered" });
  const record = { grumeId, species, volumeM3: Number(volumeM3),
    diameterCm: Number(diameterCm) || null, lengthM: Number(lengthM) || null,
    harvestDate: harvestDate || null, origin: origin || "", gps: gps || "", registeredAt: now() };
  ledger.timber[grumeId] = record;
  ledger.pendingTransactions.push({ id: crypto.randomUUID(), type: "TIMBER_REGISTERED",
    grumeId, timestamp: now(), data: record });
  minePending(ledger);
  writeLedger(ledger);
  res.status(201).json({ message: "Timber registered and committed to blockchain", timber: record,
    latestBlock: ledger.chain[ledger.chain.length - 1] });
});
app.post("/api/v1/events", (req, res) => {
  const { grumeId, eventType, actor, location, notes } = req.body || {};
  if (!grumeId || !eventType) return res.status(400).json({ error: "grumeId and eventType are required" });
  const ledger = readLedger();
  if (!ledger.timber[grumeId]) return res.status(404).json({ error: "Unknown grumeId. Register timber first." });
  const tx = { id: crypto.randomUUID(), type: "TRACEABILITY_EVENT", grumeId,
    eventType, actor: actor || "", location: location || "", notes: notes || "", timestamp: now() };
  ledger.pendingTransactions.push(tx);
  minePending(ledger);
  writeLedger(ledger);
  res.status(201).json({ message: "Event committed to blockchain", transaction: tx,
    latestBlock: ledger.chain[ledger.chain.length - 1] });
});
function minePending(ledger) {
  if (!ledger.pendingTransactions.length) return null;
  const previous = ledger.chain[ledger.chain.length - 1];
  const block = createBlock(ledger.chain.length, ledger.pendingTransactions.splice(0), previous.hash);
  ledger.chain.push(block);
  return block;
}
app.get("/api/v1/timber/:grumeId/history", (req, res) => {
  const ledger = readLedger();
  const grumeId = req.params.grumeId;
  if (!ledger.timber[grumeId]) return res.status(404).json({ error: "Timber not found" });
  const history = ledger.chain.flatMap(b => b.transactions
    .filter(tx => tx.grumeId === grumeId)
    .map(tx => ({ blockIndex: b.index, blockHash: b.hash, ...tx })));
  res.json({ grumeId, timber: ledger.timber[grumeId], history });
});
app.get("/api/v1/ledger/verify", (_req, res) => {
  const chain = readLedger().chain;
  const issues = [];
  for (let i = 0; i < chain.length; i++) {
    const b = chain[i];
    if (b.hash !== blockHash(b)) issues.push(`Block ${i}: hash mismatch`);
    if (i > 0 && b.previousHash !== chain[i - 1].hash) issues.push(`Block ${i}: previousHash mismatch`);
    if (b.index !== i) issues.push(`Block ${i}: invalid index`);
  }
  res.json({ valid: issues.length === 0, blocksChecked: chain.length, issues, checkedAt: now() });
});
app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: "Internal server error" });
});
readLedger();
app.listen(PORT, "127.0.0.1", () => {
  console.log("==============================================");
  console.log("  FOREST TRACEABILITY BLOCKCHAIN API");
  console.log("==============================================");
  console.log(`  URL:       http://127.0.0.1:${PORT}`);
  console.log(`  Ledger:    SHA-256 hash-linked local chain`);
  console.log(`  Data file: ${LEDGER_FILE}`);
  console.log("  Press Ctrl+C to stop.");
  console.log("==============================================");
});
