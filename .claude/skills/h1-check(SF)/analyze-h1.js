#!/usr/bin/env node
// H1 issue summarizer for a single crawl.
//
// Input: ONE NDJSON export of the Screaming Frog "H1 / All" element (one row per
// internal HTML page), read from --input <file> or, if omitted, from stdin.
// Each row carries: Address, Occurrences, H1-1, H1-1 Length, H1-2, H1-2 Length,
// Indexability, Indexability Status.
//
// The Screaming Frog MCP only exposes the "All" filter, so this script classifies the
// three H1 problems itself instead of relying on SF's Missing/Duplicate/Multiple buckets:
//   - missing   : page has no H1 (H1-1 blank / Occurrences 0)
//   - multiple  : page has more than one H1 (Occurrences > 1)
//   - duplicate : same H1 string shared by 2+ indexable pages
//
// Output: a JSON report is printed to stdout. No files are written — the caller turns the
// stdout into a chat summary (stateless: nothing is persisted to the repo).
//
// Usage:
//   node analyze-h1.js --input <h1-all.ndjson>
//   sf-export ... | node analyze-h1.js            # reads NDJSON from stdin

const fs = require('fs');

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--input') out.input = argv[++i];
    else if (a === '-h' || a === '--help') out.help = true;
  }
  return out;
}

const args = parseArgs(process.argv);
if (args.help) {
  console.error('Usage: analyze-h1.js --input <h1-all.ndjson>   (or pipe NDJSON on stdin)');
  process.exit(0);
}

const raw = (args.input ? fs.readFileSync(args.input, 'utf8') : fs.readFileSync(0, 'utf8')).trim();
const rows = raw
  ? raw.split('\n').map(line => { try { return JSON.parse(line); } catch { return null; } }).filter(Boolean)
  : [];

function toInt(v) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : 0;
}
function isIndexable(indexability) {
  const s = indexability || '';
  return /indexable/i.test(s) && !/non-indexable/i.test(s);
}
function pick(row) {
  return {
    address: row.Address || row.URL || '',
    indexability: row.Indexability || '',
    occurrences: toInt(row.Occurrences),
    h1_1: (row['H1-1'] || '').trim(),
    h1_2: (row['H1-2'] || '').trim(),
    h1_1_length: row['H1-1 Length'] || null,
  };
}

const pages = rows.map(pick);

// missing: no H1 text on the page
const missing = pages.filter(p => !p.h1_1);
// multiple: more than one <h1> on the page
const multiple = pages.filter(p => p.occurrences > 1 || (p.h1_2 && p.occurrences === 0));
// duplicate: same H1 string across 2+ indexable pages
const dupeGroups = new Map();
for (const p of pages) {
  if (!p.h1_1 || !isIndexable(p.indexability)) continue;
  if (!dupeGroups.has(p.h1_1)) dupeGroups.set(p.h1_1, []);
  dupeGroups.get(p.h1_1).push(p.address);
}
const duplicateClusters = [...dupeGroups.entries()]
  .filter(([, urls]) => urls.length > 1)
  .map(([h1, urls]) => ({ h1, count: urls.length, urls }))
  .sort((a, b) => b.count - a.count);
const duplicate = duplicateClusters.flatMap(c => c.urls.map(address => ({ address, h1_1: c.h1 })));

const out = {
  totals: {
    pagesAnalyzed: pages.length,
    missing: missing.length,
    multiple: multiple.length,
    duplicatePages: duplicate.length,
    duplicateClusters: duplicateClusters.length,
  },
  samples: {
    missing: missing.slice(0, 20),
    multiple: multiple.slice(0, 20),
    duplicateClusters: duplicateClusters.slice(0, 10),
  },
  full: { missing, multiple, duplicate, duplicateClusters },
};

console.log(JSON.stringify(out, null, 2));
