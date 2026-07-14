#!/usr/bin/env node
// Per-site crawl profile loader/saver/validator.
// See CLAUDE.md "Universal workflow" for how this fits in.

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const PROJECT_ROOT = path.resolve(ROOT, '..');
const PROFILES_DIR = path.join(ROOT, 'profiles');
const SKILLS_DIR = path.join(PROJECT_ROOT, '.claude', 'skills');

const DEFAULTS = {
  site_url: '',
  sitemap_urls: [],
  max_crawl_depth: 10,
  near_duplicates: false,
  include_patterns: [],
  exclude_patterns: [],
  custom_extractions: [],
  render_mode: 'html',
  max_threads: 5,
  crawl_delay_ms: 0,
  last_updated: '',
};

function profilePath(slug) {
  if (!slug || /[\/\\]/.test(slug)) throw new Error(`invalid slug: ${slug}`);
  return path.join(PROFILES_DIR, `${slug}.json`);
}

function load(slug) {
  const p = profilePath(slug);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function save(slug, profile) {
  fs.mkdirSync(PROFILES_DIR, { recursive: true });
  const merged = { ...DEFAULTS, ...profile, last_updated: new Date().toISOString() };
  fs.writeFileSync(profilePath(slug), JSON.stringify(merged, null, 2) + '\n');
  return merged;
}

function init(slug, overrides = {}) {
  const existing = load(slug);
  if (existing) return existing;
  return save(slug, { ...DEFAULTS, ...overrides });
}

function readSkillRequires(skillName) {
  const skillFile = path.join(SKILLS_DIR, skillName, 'SKILL.md');
  if (!fs.existsSync(skillFile)) throw new Error(`skill not found: ${skillName}`);
  const text = fs.readFileSync(skillFile, 'utf8');
  const fm = text.match(/^---\n([\s\S]*?)\n---/);
  if (!fm) return {};
  return parseRequiresBlock(fm[1]);
}

// Minimal YAML reader scoped to the `requires:` block shape used by SKILL.md.
// Supports: top-level keys, nested maps, inline `[a, b]` arrays, booleans, numbers, strings.
function parseRequiresBlock(yaml) {
  const lines = yaml.split('\n');
  const start = lines.findIndex(l => /^requires:\s*$/.test(l));
  if (start === -1) return {};
  const block = [];
  for (let i = start + 1; i < lines.length; i++) {
    if (/^\S/.test(lines[i])) break;
    block.push(lines[i]);
  }
  return parseNested(block, 2);
}

function parseNested(lines, indent) {
  const out = {};
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(\s+)([\w-]+):\s*(.*)$/);
    if (!m || m[1].length !== indent) continue;
    const key = m[2];
    const rest = m[3].trim();
    if (rest === '') {
      const sub = [];
      for (let j = i + 1; j < lines.length; j++) {
        const im = lines[j].match(/^(\s+)/);
        if (!im || im[1].length <= indent) break;
        sub.push(lines[j]);
      }
      out[key] = parseNested(sub, indent + 2);
    } else if (rest.startsWith('[') && rest.endsWith(']')) {
      out[key] = rest.slice(1, -1).split(',').map(s => s.trim()).filter(Boolean);
    } else if (rest === '{}') {
      out[key] = {};
    } else if (rest === 'true' || rest === 'false') {
      out[key] = rest === 'true';
    } else if (/^-?\d+(\.\d+)?$/.test(rest)) {
      out[key] = Number(rest);
    } else {
      out[key] = rest.replace(/^["']|["']$/g, '');
    }
  }
  return out;
}

function check(slug, skillName) {
  const profile = load(slug);
  if (!profile) return { ok: false, missing: [{ reason: 'profile-not-found', slug }] };
  const requires = readSkillRequires(skillName);
  const profReqs = (requires.profile && typeof requires.profile === 'object') ? requires.profile : {};
  const missing = [];
  for (const [key, want] of Object.entries(profReqs)) {
    if (JSON.stringify(profile[key]) !== JSON.stringify(want)) {
      missing.push({ field: key, expected: want, actual: profile[key] });
    }
  }
  return { ok: missing.length === 0, missing, requires };
}

function readStdin() {
  return fs.readFileSync(0, 'utf8');
}

function main() {
  const [, , cmd, ...rest] = process.argv;
  try {
    if (cmd === '--load') {
      const profile = load(rest[0]);
      if (!profile) process.exit(1);
      process.stdout.write(JSON.stringify(profile, null, 2) + '\n');
    } else if (cmd === '--save') {
      const input = JSON.parse(readStdin());
      const saved = save(rest[0], input);
      process.stdout.write(JSON.stringify(saved, null, 2) + '\n');
    } else if (cmd === '--init') {
      const saved = init(rest[0]);
      process.stdout.write(JSON.stringify(saved, null, 2) + '\n');
    } else if (cmd === '--check') {
      const [slug, skill] = rest;
      const result = check(slug, skill);
      process.stdout.write(JSON.stringify(result, null, 2) + '\n');
      process.exit(result.ok ? 0 : 1);
    } else {
      console.error('Usage: profile.js --load <slug>');
      console.error('       profile.js --save <slug>   (reads JSON from stdin)');
      console.error('       profile.js --init <slug>');
      console.error('       profile.js --check <slug> <skill-name>');
      process.exit(2);
    }
  } catch (err) {
    console.error(err.message);
    process.exit(2);
  }
}

if (require.main === module) main();

module.exports = { load, save, init, check, readSkillRequires, DEFAULTS };
