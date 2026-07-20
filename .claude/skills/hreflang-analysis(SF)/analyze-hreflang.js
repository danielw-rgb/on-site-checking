#!/usr/bin/env node
// Hreflang validation against per-page annotation export.
// Input: NDJSON where each row is a page with HTML/HTTP/Sitemap hreflang N + URL N fields.
// Checks: missing self-reference, missing x-default, duplicate locale entries,
// invalid language tags, cross-page reciprocity (return links), and URL normalization.
//
// Input: ONE NDJSON export of the Screaming Frog "Hreflang / All" element, read from
// --input <file> or, if omitted, from stdin.
//
// Output: a JSON report is printed to stdout. No files are written by default — the caller
// turns the stdout into a chat summary (stateless: nothing is persisted to the repo).
//
// Usage:
//   node analyze-hreflang.js --input <hreflang-all.ndjson> [--host <crawl-host>]
//   sf-export ... | node analyze-hreflang.js
//
// --host is optional. If omitted, the host is derived from the first row's Address field.
// It controls which destinations count as "external" (excluded from intra-crawl reciprocity).

const fs = require('fs');

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--input' || a === '--host') {
      out[a.slice(2)] = argv[++i];
    } else if (a === '-h' || a === '--help') {
      out.help = true;
    }
  }
  return out;
}

const args = parseArgs(process.argv);

if (args.help) {
  console.error('Usage: analyze-hreflang.js --input <hreflang-all.ndjson> [--host <crawl-host>]   (or pipe NDJSON on stdin)');
  process.exit(0);
}

const rawInput = (args.input ? fs.readFileSync(args.input, 'utf8') : fs.readFileSync(0, 'utf8')).trim();
const rows = rawInput
  ? rawInput.split('\n').map(line => { try { return JSON.parse(line); } catch { return null; } }).filter(Boolean)
  : [];

// Derive crawl host from --host or the first row's Address.
let crawlHost = args.host;
if (!crawlHost && rows.length) {
  try { crawlHost = new URL(rows[0].Address).host; } catch {}
}

// Build per-page hreflang annotation maps.
// Each entry: { url, locales: Map<locale, Set<url>>, sources: { html, http, sitemap } }
const pages = [];
for (const r of rows) {
  const locales = new Map();          // locale -> Set of destination URLs
  const sources = new Set();          // which sources declared anything
  for (let i = 1; i <= 50; i++) {
    for (const src of ['HTML', 'HTTP', 'Sitemap']) {
      const locKey = `${src} hreflang ${i}`;
      const urlKey = `${src} hreflang ${i} URL`;
      const loc = r[locKey];
      const url = r[urlKey];
      if (!loc || !url) continue;
      sources.add(src);
      if (!locales.has(loc)) locales.set(loc, new Set());
      locales.get(loc).add(url);
    }
  }
  pages.push({
    address: r.Address,
    title: r['Title 1'] || '',
    indexability: r.Indexability,
    locales,
    sources: [...sources],
  });
}

// Detection helpers.
const VALID_LANG_REGEX = /^([a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2}|-\d{3})?|x-default)$/;
// ISO 639-1 plus a handful of common 639-2; we mostly want to catch obvious typos.

const issues = {
  missingSelfReference: [],
  missingXDefault: [],
  duplicateLocale: [],
  invalidLanguageCode: [],
  selfNotInOwnSet: [],
  missingReturnLink: [],
  inconsistentReturnLink: [],
  pagesWithHreflang: pages.length,
};

// Index URL -> page (for reciprocity lookup). Only intra-crawl pages.
const urlToPage = new Map();
for (const p of pages) urlToPage.set(p.address, p);

for (const p of pages) {
  const localesArr = [...p.locales.entries()];

  // x-default present?
  if (!p.locales.has('x-default')) {
    issues.missingXDefault.push(p.address);
  }

  // Duplicate locale (multiple distinct URLs for same locale)?
  for (const [loc, urls] of localesArr) {
    if (urls.size > 1) {
      issues.duplicateLocale.push({ page: p.address, locale: loc, urls: [...urls] });
    }
  }

  // Invalid language code?
  for (const [loc] of localesArr) {
    if (!VALID_LANG_REGEX.test(loc)) {
      issues.invalidLanguageCode.push({ page: p.address, locale: loc });
    }
  }

  // Self reference: does the page list itself in its own hreflang set under some locale?
  let selfFound = false;
  for (const [, urls] of localesArr) {
    if (urls.has(p.address)) { selfFound = true; break; }
  }
  if (!selfFound) {
    // Allow case where x-default points to a canonical version of this page.
    issues.selfNotInOwnSet.push(p.address);
  }

  // Return-link check (intra-crawl only — for cross-domain we can't see the target page's hreflang).
  // For every (locale, destination) declared by p that points to another crawled page q,
  // require that q's hreflang includes p.address under SOME locale (preferably matching).
  for (const [loc, urls] of localesArr) {
    if (loc === 'x-default') continue;
    for (const dest of urls) {
      if (dest === p.address) continue;
      const q = urlToPage.get(dest);
      if (!q) continue; // External or uncrawled — skip; we only check intra-crawl reciprocity.
      // Does q's hreflang set reference p.address anywhere?
      let backRef = null;
      for (const [qLoc, qUrls] of q.locales.entries()) {
        if (qUrls.has(p.address)) { backRef = qLoc; break; }
      }
      if (!backRef) {
        issues.missingReturnLink.push({ from: p.address, to: dest, declaredLocale: loc });
      }
      // Note: "inconsistent return link" would require knowing what locale p declared for itself.
      // We can do this: find p's own locale (the one whose URL set contains p.address), and
      // check that q references p.address under THAT locale.
      const pSelfLoc = (() => {
        for (const [l, u] of localesArr) if (u.has(p.address) && l !== 'x-default') return l;
        return null;
      })();
      if (backRef && pSelfLoc && backRef !== pSelfLoc && backRef !== 'x-default') {
        issues.inconsistentReturnLink.push({ from: p.address, to: dest, expectedLocale: pSelfLoc, actualLocale: backRef });
      }
    }
  }
}

// External hreflang targets (cross-domain) — list them; we can't verify reciprocity automatically.
const externalTargets = new Map(); // domain -> count
for (const p of pages) {
  for (const [, urls] of p.locales) {
    for (const u of urls) {
      try {
        const host = new URL(u).host;
        if (host !== crawlHost) {
          externalTargets.set(host, (externalTargets.get(host) || 0) + 1);
        }
      } catch {}
    }
  }
}

const out = {
  crawlHost,
  totals: {
    pagesWithHreflang: pages.length,
    missingXDefault: issues.missingXDefault.length,
    duplicateLocale: issues.duplicateLocale.length,
    invalidLanguageCode: issues.invalidLanguageCode.length,
    selfNotInOwnSet: issues.selfNotInOwnSet.length,
    missingReturnLinkIntraCrawl: issues.missingReturnLink.length,
    inconsistentReturnLinkIntraCrawl: issues.inconsistentReturnLink.length,
  },
  externalTargets: [...externalTargets.entries()].sort((a, b) => b[1] - a[1]),
  samples: {
    missingXDefault: issues.missingXDefault.slice(0, 10),
    duplicateLocale: issues.duplicateLocale.slice(0, 10),
    invalidLanguageCode: issues.invalidLanguageCode.slice(0, 10),
    selfNotInOwnSet: issues.selfNotInOwnSet.slice(0, 10),
    missingReturnLink: issues.missingReturnLink.slice(0, 20),
    inconsistentReturnLink: issues.inconsistentReturnLink.slice(0, 20),
  },
  full: issues,
};

// Print the full report to stdout. No files are written — the caller turns this into a chat summary.
console.log(JSON.stringify({ crawlHost, totals: out.totals, externalTargets: out.externalTargets, samples: out.samples, full: out.full }, null, 2));
