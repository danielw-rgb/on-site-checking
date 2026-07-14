#!/usr/bin/env node
// H1 issue summarizer for a single crawl run.
// Input: ./crawls/<slug>/<run-id>/ containing h1-missing.ndjson, h1-duplicate.ndjson, h1-multiple.ndjson.
// Output: JSON report at --output + compact summary on stdout.
//         A CSV (columns: URL, Issue, H1-1, H1-2) is also written, one row per (URL, issue)
//         pair, at the same path as --output but with .csv extension (or at --csv).
//
// Usage:
//   node analyze-h1.js --run-dir <dir> --output <json> [--csv <csv>]

const fs = require('fs');
const path = require('path');

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--run-dir' || a === '--output' || a === '--csv') out[a.slice(2)] = argv[++i];
    else if (a === '-h' || a === '--help') out.help = true;
  }
  return out;
}

const args = parseArgs(process.argv);
const runDirKey = 'run-dir';
if (args.help || !args[runDirKey] || !args.output) {
  console.error('Usage: analyze-h1.js --run-dir <crawl-run-dir> --output <json>');
  process.exit(args.help ? 0 : 1);
}

function readNdjson(file) {
  if (!fs.existsSync(file)) return [];
  const text = fs.readFileSync(file, 'utf8').trim();
  if (!text) return [];
  return text.split('\n').map(line => {
    try { return JSON.parse(line); } catch { return null; }
  }).filter(Boolean);
}

const runDir = args[runDirKey];
const missingRows = readNdjson(path.join(runDir, 'h1-missing.ndjson'));
const duplicateRows = readNdjson(path.join(runDir, 'h1-duplicate.ndjson'));
const multipleRows = readNdjson(path.join(runDir, 'h1-multiple.ndjson'));

function pick(row) {
  return {
    address: row.Address || row.URL || '',
    indexability: row.Indexability || '',
    title: row['Title 1'] || '',
    h1_1: row['H1-1'] || '',
    h1_2: row['H1-2'] || '',
    h1_1_length: row['H1-1 Length'] || null,
  };
}

const missing = missingRows.map(pick);
const duplicate = duplicateRows.map(pick);
const multiple = multipleRows.map(pick);

// Group duplicates by H1 string so the user sees which H1s collide.
const dupeGroups = new Map();
for (const e of duplicate) {
  const key = (e.h1_1 || '').trim();
  if (!key) continue;
  if (!dupeGroups.has(key)) dupeGroups.set(key, []);
  dupeGroups.get(key).push(e.address);
}
const duplicateClusters = [...dupeGroups.entries()]
  .map(([h1, urls]) => ({ h1, count: urls.length, urls }))
  .sort((a, b) => b.count - a.count);

const out = {
  totals: {
    missing: missing.length,
    duplicate: duplicate.length,
    multiple: multiple.length,
    duplicateClusters: duplicateClusters.length,
  },
  samples: {
    missing: missing.slice(0, 20),
    duplicate: duplicate.slice(0, 20),
    multiple: multiple.slice(0, 20),
    duplicateClusters: duplicateClusters.slice(0, 10),
  },
  full: {
    missing,
    duplicate,
    multiple,
    duplicateClusters,
  },
};

fs.mkdirSync(path.dirname(args.output), { recursive: true });
fs.writeFileSync(args.output, JSON.stringify(out, null, 2));

// CSV: one row per (URL, issue) pair so the table reads top-to-bottom by issue type.
function csvCell(v) {
  const s = v == null ? '' : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
function csvRow(cells) { return cells.map(csvCell).join(','); }

const csvRows = [csvRow(['URL', 'Issue', 'H1-1', 'H1-2'])];
for (const r of missing)   csvRows.push(csvRow([r.address, 'Missing H1',   '',      '']));
for (const r of duplicate) csvRows.push(csvRow([r.address, 'Duplicate H1', r.h1_1,  '']));
for (const r of multiple)  csvRows.push(csvRow([r.address, 'Multiple H1',  r.h1_1,  r.h1_2]));

const csvPath = args.csv || args.output.replace(/\.json$/i, '.csv');
fs.writeFileSync(csvPath, csvRows.join('\n') + '\n');

console.log(JSON.stringify({ totals: out.totals, samples: out.samples, csv: csvPath }, null, 2));
