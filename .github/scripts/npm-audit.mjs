// npm audit with a dated list of accepted advisories (.github/security/npm-audit-ignore.json).
// Fails on any high or critical advisory that is not listed, and on any listed exception past its date.
// Usage, from the npm project folder: node npm-audit.mjs <ignore file> [<npm audit JSON report>]
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const BLOCKING = new Set(['high', 'critical']);
const [ignoreFile, reportFile] = process.argv.slice(2);
if (!ignoreFile) {
  console.error('usage: node npm-audit.mjs <ignore file> [<npm audit JSON report>]');
  process.exit(2);
}

function auditReport() {
  if (reportFile) return readFileSync(reportFile, 'utf8');
  try {
    return execFileSync('npm', ['audit', '--omit=dev', '--json'], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  } catch (error) {
    // npm audit exits with 1 when it finds something: the report is still on stdout
    if (error.stdout) return error.stdout;
    throw error;
  }
}

const today = new Date().toISOString().slice(0, 10);
const exceptions = JSON.parse(readFileSync(ignoreFile, 'utf8'));
const report = JSON.parse(auditReport());
if (report.error) {
  console.error(`npm audit failed: ${report.error.summary ?? JSON.stringify(report.error)}`);
  process.exit(2);
}

// Each advisory once, whatever the number of packages that pull it
const advisories = new Map();
for (const vulnerability of Object.values(report.vulnerabilities ?? {})) {
  for (const via of vulnerability.via) {
    if (typeof via === 'object' && BLOCKING.has(via.severity)) {
      const id = via.url.split('/').pop();
      advisories.set(id, { id, package: via.name, title: via.title, severity: via.severity, url: via.url });
    }
  }
}

let failed = false;
const used = new Set();
let accepted = 0;
for (const advisory of advisories.values()) {
  const exception = exceptions.find((e) => e.id === advisory.id);
  if (exception) used.add(exception.id);
  if (!exception) {
    console.error(`::error::${advisory.severity} ${advisory.package}: ${advisory.title} (${advisory.url})`);
    failed = true;
  } else if (exception.until < today) {
    console.error(`::error::Exception ${advisory.id} expired on ${exception.until}: check for a fix, then remove it or push the date`);
    failed = true;
  } else {
    accepted += 1;
    console.log(`::warning::${advisory.id} (${advisory.package}) accepted until ${exception.until}: ${exception.reason}`);
  }
}
for (const exception of exceptions.filter((e) => !used.has(e.id))) {
  console.log(`::warning::Exception ${exception.id} no longer matches anything: remove it from ${ignoreFile}`);
}
console.log(`${advisories.size} high or critical advisory(ies), ${accepted} accepted`);
process.exit(failed ? 1 : 0);
