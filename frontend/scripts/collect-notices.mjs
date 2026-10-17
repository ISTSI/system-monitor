import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';

const destination = resolve('../third_party/frontend');
mkdirSync(destination, { recursive: true });
const lock = JSON.parse(readFileSync('package-lock.json', 'utf8'));
const inventory = [];
for (const [path, entry] of Object.entries(lock.packages)) {
  if (!path || !existsSync(join(path, 'package.json'))) continue;
  const metadata = JSON.parse(readFileSync(join(path, 'package.json'), 'utf8'));
  const id = `${metadata.name.replaceAll('/', '__')}@${metadata.version}`;
  const licenses = readdirSync(path).filter(name => /^(licen[cs]e|notice|copying)([-._]|$)/i.test(name));
  if (!licenses.length) {
    licenses.push('package.json');
    if (existsSync(join(path, 'README.md'))) licenses.push('README.md');
  }
  const notices = [];
  for (const name of licenses) {
    const source = join(path, name);
    if (!readFileSync(source).length) continue;
    const savedName = name === 'README.md' ? 'README.txt' : name;
    const target = join(destination, id, savedName);
    mkdirSync(dirname(target), { recursive: true });
    copyFileSync(source, target);
    notices.push({ path: `${id}/${basename(savedName)}`, sha256: createHash('sha256').update(readFileSync(source)).digest('hex') });
  }
  inventory.push({
    name: metadata.name, version: metadata.version, license: metadata.license ?? entry.license ?? 'UNDECLARED',
    development: Boolean(entry.dev), resolved: entry.resolved, integrity: entry.integrity, notices,
  });
}
inventory.sort((a, b) => a.name.localeCompare(b.name));
writeFileSync(join(destination, 'inventory.json'), JSON.stringify({ packages: inventory }, null, 2) + '\n');
const lines = ['# Frontend dependency notices', '',
  'Collected from the actually installed npm lockfile. Runtime and development dependencies use free/open-source licenses; no paid component is required.', '',
  '| Package | Version | License | Scope |', '|---|---|---|---|',
  ...inventory.map(item => `| ${item.name} | ${item.version} | ${String(item.license).replaceAll('|', '/')} | ${item.development ? 'Development' : 'Runtime'} |`), '',
  'Original license/notice texts are preserved in the adjacent package directories. See inventory.json for artifact integrity and per-notice hashes.', '',
];
writeFileSync(join(destination, 'README.md'), lines.join('\n'));
console.log(`Collected notices for ${inventory.length} installed packages.`);
