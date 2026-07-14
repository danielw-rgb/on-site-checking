#!/usr/bin/env node
// Per-run crawl manifest manager.
// See CLAUDE.md "Universal workflow" — step 2 (--init) and step 4a (--has/--add).

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const PROJECT_ROOT = path.resolve(ROOT, '..');
const CRAWLS_DIR = path.join(ROOT, 'crawls');
const SKILLS_DIR = path.join(PROJECT_ROOT, '.claude', 'skills');
const SCHEMA_VERSION = 1;

function runDir(slug, runId) {
  if (!slug || /[\/\\]/.test(slug)) throw new Error(`invalid slug: ${slug}`);
  if (!runId || /[\/\\]/.test(runId)) throw new Error(`invalid run id: ${runId}`);
  return path.join(CRAWLS_DIR, slug, runId);
}

function manifestPath(slug, runId) {
  return path.join(runDir(slug, runId), 'manifest.json');
}

function load(slug, runId) {
  const p = manifestPath(slug, runId);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function writeAtomic(p, obj) {
  const tmp = p + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + '\n');
  fs.renameSync(tmp, p);
}

function init(slug, runId, meta) {
  const dir = runDir(slug, runId);
  fs.mkdirSync(dir, { recursive: true });
  const p = manifestPath(slug, runId);
  if (fs.existsSync(p)) {
    throw new Error(`manifest already exists: ${p}`);
  }
  const manifest = {
    schema_version: SCHEMA_VERSION,
    site_url: meta.site_url || '',
    domain_slug: slug,
    run_id: runId,
    sf_crawl_id: meta.sf_crawl_id || null,
    crawl_started_at: meta.crawl_started_at || null,
    crawl_finished_at: meta.crawl_finished_at || null,
    total_urls_crawled: meta.total_urls_crawled ?? null,
    profile_snapshot: meta.profile_snapshot || {},
    exports: [],
  };
  writeAtomic(p, manifest);
  return manifest;
}

function has(slug, runId, exportSlug) {
  const manifest = load(slug, runId);
  if (!manifest) return false;
  const entry = manifest.exports.find(e => e.slug === exportSlug);
  if (!entry) return false;
  return fs.existsSync(path.join(runDir(slug, runId), entry.filename));
}

function add(slug, runId, exportSlug, entry) {
  const p = manifestPath(slug, runId);
  const manifest = load(slug, runId);
  if (!manifest) throw new Error(`manifest not found: ${p}`);
  if (!entry.filename || !entry.source) {
    throw new Error('add: entry must include filename and source');
  }
  const next = {
    slug: exportSlug,
    filename: entry.filename,
    source: entry.source,
    row_count: entry.row_count ?? null,
    exported_at: new Date().toISOString(),
    exported_by_skill: entry.exported_by_skill || null,
  };
  manifest.exports = manifest.exports.filter(e => e.slug !== exportSlug);
  manifest.exports.push(next);
  writeAtomic(p, manifest);
  return next;
}

// Read a skill's `requires.exports` list. Each entry is {slug, source: {...}}.
// Scoped reader — handles the list-of-maps shape that profile.js's parser doesn't.
function readSkillExports(skillName) {
  const skillFile = path.join(SKILLS_DIR, skillName, 'SKILL.md');
  if (!fs.existsSync(skillFile)) throw new Error(`skill not found: ${skillName}`);
  const text = fs.readFileSync(skillFile, 'utf8');
  const fm = text.match(/^---\n([\s\S]*?)\n---/);
  if (!fm) return [];
  const lines = fm[1].split('\n');
  const reqIdx = lines.findIndex(l => /^requires:\s*$/.test(l));
  if (reqIdx === -1) return [];
  const expIdx = lines.findIndex((l, i) => i > reqIdx && /^\s{2}exports:\s*$/.test(l));
  if (expIdx === -1) return [];
  const block = [];
  for (let i = expIdx + 1; i < lines.length; i++) {
    if (/^\S/.test(lines[i])) break;
    if (/^\s{0,1}\S/.test(lines[i])) break;
    block.push(lines[i]);
  }
  return parseExportsList(block);
}

function parseExportsList(lines) {
  const items = [];
  let current = null;
  for (const raw of lines) {
    const item = raw.match(/^\s{4}-\s+(.*)$/);
    if (item) {
      if (current) items.push(current);
      current = {};
      const inline = item[1].match(/^([\w-]+):\s*(.*)$/);
      if (inline) assignScalar(current, inline[1], inline[2]);
      continue;
    }
    if (!current) continue;
    const kv = raw.match(/^\s{6}([\w-]+):\s*(.*)$/);
    if (kv) {
      const key = kv[1];
      const val = kv[2].trim();
      if (val === '') {
        current[key] = {};
        current.__lastNestedKey = key;
      } else if (val.startsWith('{') && val.endsWith('}')) {
        current[key] = parseInlineMap(val);
      } else {
        assignScalar(current, key, val);
      }
      continue;
    }
    const nested = raw.match(/^\s{8}([\w-]+):\s*(.*)$/);
    if (nested && current.__lastNestedKey) {
      const target = current[current.__lastNestedKey];
      if (target && typeof target === 'object') {
        assignScalar(target, nested[1], nested[2]);
      }
    }
  }
  if (current) items.push(current);
  return items.map(({ __lastNestedKey, ...rest }) => rest);
}

function parseInlineMap(s) {
  const out = {};
  const body = s.slice(1, -1);
  for (const pair of body.split(',')) {
    const [k, ...vs] = pair.split(':');
    if (!k) continue;
    assignScalar(out, k.trim(), vs.join(':').trim());
  }
  return out;
}

function assignScalar(obj, key, raw) {
  const v = String(raw).trim().replace(/^["']|["']$/g, '');
  if (v === 'true' || v === 'false') obj[key] = v === 'true';
  else if (/^-?\d+(\.\d+)?$/.test(v)) obj[key] = Number(v);
  else obj[key] = v;
}

function readStdin() {
  return fs.readFileSync(0, 'utf8');
}

function main() {
  const [, , cmd, ...rest] = process.argv;
  try {
    if (cmd === '--init') {
      const [slug, runId] = rest;
      const meta = JSON.parse(readStdin() || '{}');
      const m = init(slug, runId, meta);
      process.stdout.write(JSON.stringify(m, null, 2) + '\n');
    } else if (cmd === '--get') {
      const [slug, runId] = rest;
      const m = load(slug, runId);
      if (!m) process.exit(1);
      process.stdout.write(JSON.stringify(m, null, 2) + '\n');
    } else if (cmd === '--has') {
      const [slug, runId, exportSlug] = rest;
      process.exit(has(slug, runId, exportSlug) ? 0 : 1);
    } else if (cmd === '--add') {
      const [slug, runId, exportSlug] = rest;
      const entry = JSON.parse(readStdin());
      const written = add(slug, runId, exportSlug, entry);
      process.stdout.write(JSON.stringify(written, null, 2) + '\n');
    } else if (cmd === '--skill-exports') {
      const [skill] = rest;
      process.stdout.write(JSON.stringify(readSkillExports(skill), null, 2) + '\n');
    } else {
      console.error('Usage: manifest.js --init <slug> <run-id>             (reads metadata JSON from stdin)');
      console.error('       manifest.js --get  <slug> <run-id>');
      console.error('       manifest.js --has  <slug> <run-id> <export-slug>');
      console.error('       manifest.js --add  <slug> <run-id> <export-slug> (reads entry JSON from stdin)');
      console.error('       manifest.js --skill-exports <skill-name>');
      process.exit(2);
    }
  } catch (err) {
    console.error(err.message);
    process.exit(2);
  }
}

if (require.main === module) main();

module.exports = { init, load, has, add, readSkillExports, SCHEMA_VERSION };
