import { readFileSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const cacheRoot = resolve('../.cache');
mkdirSync(cacheRoot, { recursive: true });
const work = mkdtempSync(join(cacheRoot, 'inspector-api-'));
if (dirname(resolve(work)) !== cacheRoot || !basename(work).startsWith('inspector-api-')) {
  throw new Error('Refusing API type cleanup outside its repository-local temporary directory.');
}
try {
  const output = join(work, 'schema.d.ts');
  const generation = spawnSync(process.execPath, [
    resolve('node_modules/openapi-typescript/bin/cli.js'), '../backend/openapi.json', '-o', output,
  ], { stdio: 'pipe', encoding: 'utf8' });
  if (generation.status !== 0) throw new Error('API type generation failed.');
  if (readFileSync(output, 'utf8') !== readFileSync('src/api/schema.d.ts', 'utf8')) {
    throw new Error('Generated API types are stale; run npm run api:generate.');
  }
  console.log('Generated API types match backend/openapi.json.');
} finally {
  rmSync(work, { recursive: true, force: true });
}
