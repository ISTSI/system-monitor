import { expect, test } from '@playwright/test';
import { execFile, spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { serveBuiltAssets, submitSignIn } from './ui';
import type { components } from '../src/api/schema';
import { defaultGeometry, type Config, type Topology } from '../src/topology';

const root = resolve('..');
const identifier = process.env.INSPECTOR_E2E_SOAK_RUN ?? '';
const enabled = process.env.INSPECTOR_E2E_URL === 'https://localhost:8449' && /^[a-f0-9]{12}$/.test(identifier);
const fixture = enabled ? JSON.parse(readFileSync(resolve(root, '.state/stage7-browser/public-fixture.json'), 'utf8')) as { synthetic: boolean; host: string; port: number; username: string; projects: string[] } : null;
if (enabled && (!fixture?.synthetic || fixture.host !== 'stage7-sftp' || fixture.port !== 8022 || fixture.projects.join(',') !== 'stage7-fixture-a,stage7-fixture-b')) throw new Error('Only the existing generated Stage 07 synthetic fixture is authorized.');
const project = 'stage7-fixture-a';
const prefix = `soak-${identifier}`;
const firstView = `${prefix}-all`; const secondView = `${prefix}-second-view`;
const output = resolve(root, 'verification/stage-7');
const python = process.env.INSPECTOR_TEST_PYTHON ?? resolve(root, 'backend/.venv/Scripts/python.exe');
const controller = resolve(root, 'scripts/verify_stage7_soak.py');
const duration = 1800_000;

async function command(args: string[]): Promise<Record<string, unknown>> {
  return await new Promise((fulfill, reject) => execFile(python, [controller, ...args], { cwd: root, timeout: 45000, windowsHide: true, maxBuffer: 4 * 1024 * 1024 }, (error, stdout) => {
    if (error) reject(new Error('The bounded synthetic soak controller failed; protected data withheld.'));
    else { try { fulfill(JSON.parse(stdout) as Record<string, unknown>); } catch { reject(new Error('Invalid synthetic soak measurement.')); } }
  }));
}

async function hostBrowserProcesses(ids: number[]): Promise<unknown> {
  if (!ids.length || ids.some(id => !Number.isSafeInteger(id) || id <= 0)) throw new Error('Invalid owned Chromium process identity.');
  if (process.platform !== 'win32') return { available: false, reason: 'Windows browser RSS sampler is scoped to this acceptance host; CDP CPU/heap remains recorded.' };
  const script = `Get-Process -Id ${ids.join(',')} -ErrorAction SilentlyContinue | Select-Object Id,WorkingSet64,CPU,HandleCount,@{Name='ThreadCount';Expression={$_.Threads.Count}} | ConvertTo-Json -Compress`;
  return await new Promise((fulfill, reject) => execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], { timeout: 15000, windowsHide: true }, (error, stdout) => {
    if (error) reject(new Error('Owned Chromium resource measurement failed.'));
    else { try { fulfill(JSON.parse(stdout)); } catch { reject(new Error('Invalid owned Chromium resource measurement.')); } }
  }));
}

test.skip(!enabled, 'Requires the explicit generated Stage 07 fixture and soak run identity; ordinary browser runs never start this 30-minute workload.');

test('AT61 navigates sixty configured processes during thirty continuous minutes of five low-rate SFTP monitors', async ({ page, context, browser, baseURL }) => {
  if (existsSync(resolve(root, `.state/stage7-soak/${identifier}-restored.json`))) throw new Error('A completed soak identity cannot be reused; choose a fresh run identity.');
  test.setTimeout(40 * 60 * 1000);
  const failures: string[] = []; const external: string[] = []; let createdSockets = 0; const openSockets = new Set<unknown>();
  page.on('pageerror', error => failures.push(error.message)); context.on('page', extra => extra.on('pageerror', error => failures.push(error.message)));
  page.on('websocket', socket => { createdSockets += 1; openSockets.add(socket); socket.on('close', () => openSockets.delete(socket)); });
  await context.grantPermissions(['local-network-access'], { origin: baseURL! });
  await context.route('**/*', route => { const url = new URL(route.request().url()); if (url.origin === baseURL) return route.fallback(); external.push(url.origin); return route.abort(); });
  await serveBuiltAssets(context, baseURL!);
  const account = (JSON.parse(readFileSync(resolve(root, '.secrets/stage7-browser/accounts.json'), 'utf8')) as Record<string, { username: string; password: string }>).administrator;
  await page.goto('/'); await page.getByLabel('Username', { exact: true }).fill(account.username);
  try { await page.getByLabel('Password', { exact: true }).fill(account.password); expect((await submitSignIn(page)).status()).toBe(200); }
  catch { await page.locator('input[type="password"]').fill('').catch(() => {}); throw new Error('Existing synthetic soak sign-in failed; protected values withheld.'); }
  const original = await (await page.request.get(`/api/v1/projects/${project}/topology`)).json() as Topology;
  expect(original.config.processes).toHaveLength(5);
  const monitored = original.config.processes.map(process => process.id);
  const connections = original.config.connections ?? [];
  expect(connections.length).toBeGreaterThan(0);
  for (const connection of connections) {
    expect(connection.host).toBe(fixture!.host); expect(connection.port).toBe(8022); expect(connection.username).toBe(fixture!.username);
    expect(connection.allowed_log_roots).toEqual(['/var/log/inspector-demo']); expect(connection.jump_connection_id).toBeNull();
  }
  const { csrf_token } = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
  const headers = { Origin: baseURL!, 'X-CSRF-Token': csrf_token };
  async function reapproveExisting(revision: number) {
    for (const connection of connections) {
      const base = `/api/v1/projects/${project}/connections/${connection.id}/source-access`;
      const response = await page.request.get(base); expect(response.status()).toBe(200);
      const current = await response.json() as components['schemas']['SourceAccessResponse'];
      expect(current.roots).toEqual(['/var/log/inspector-demo']); expect(current.approval.revision).toBeGreaterThan(0);
      const result = await page.request.post(base + '/approve', { headers, data: { expected_config_revision: revision, expected_approval_revision: current.approval.revision, verified: true } });
      expect(result.status()).toBe(200); expect((await result.json() as components['schemas']['SourceAccessResponse']).approval.approved).toBe(true);
    }
  }
  for (const connection of connections) {
    const current = await (await page.request.get(`/api/v1/projects/${project}/connections/${connection.id}/source-access`)).json() as components['schemas']['SourceAccessResponse'];
    expect(current.approval.approved).toBe(true);
  }
  const config: Config = structuredClone(original.config);
  for (let index = 5; index < 60; index += 1) config.processes.push({ id: `${prefix}-process-${String(index).padStart(2, '0')}`, name: `Soak process ${String(index).padStart(2, '0')}`, server_id: config.servers[index % config.servers.length].id, description: 'Temporary generated AT61 unmonitored configured process; health unknown.', tags: ['synthetic', 'soak'], pcs_resource_name: null, log_source: structuredClone(config.processes.find(process => process.server_id === config.servers[index % config.servers.length].id)!.log_source!) });
  const nodes = defaultGeometry(config);
  config.views = [...config.views, ...[firstView, secondView].map(id => ({ id, name: id === firstView ? 'All 60 configured processes' : 'Second documented layout', nodes: structuredClone(nodes), flow_ids: config.flows.map(flow => flow.id) }))];
  const snapshotDirectory = resolve(root, '.state/stage7-soak'); mkdirSync(snapshotDirectory, { recursive: true });
  writeFileSync(resolve(snapshotDirectory, `${identifier}-original.json`), JSON.stringify(original.config, null, 2));
  let changed = false; let revision = original.revision;
  let graph: import('@playwright/test').Page | null = null;
  try {
  const saved = await page.request.put(`/api/v1/projects/${project}/topology`, { headers, data: { expected_revision: revision, config } }); expect(saved.status()).toBe(200);
  revision = (await saved.json() as Topology).revision; changed = true;
  await reapproveExisting(revision);
  await page.goto(`/systems/${project}/logs`); await expect(page.getByTestId('workspace-id')).toHaveText(/^[a-f0-9-]{36}$/);
  await page.getByRole('button', { name: /^Live monitor/ }).click();
  const choices = page.getByRole('group', { name: 'Processes to monitor', exact: true }).getByRole('checkbox');
  expect(await choices.count()).toBe(60);
  for (const id of monitored) await page.getByRole('group', { name: 'Processes to monitor', exact: true }).locator(`input[data-process-id="${id}"]`).check();
  let monitor: components['schemas']['LiveSessionResponse'] | null = null;
  for (let attempt = 0; attempt < 12 && !monitor; attempt += 1) {
    const pending = page.waitForResponse(response => response.url().endsWith('/live-sessions') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Monitor selected', exact: true }).click(); const response = await pending;
    if (response.status() === 429) { await page.waitForTimeout(15000); continue; }
    expect(response.status()).toBe(202); monitor = await response.json() as components['schemas']['LiveSessionResponse'];
  }
  expect(monitor, 'Production quotas were preserved; a soak requires five free deployment subscriptions.').not.toBeNull();
  await expect(page.getByText('Stream connected', { exact: true })).toBeVisible();
  await expect(page.locator('.live-event').first()).toBeVisible();
  graph = await context.newPage(); await graph.goto(`/systems/${project}/topology`);
  await expect(graph.getByTestId('workspace-id')).toHaveText(/^[a-f0-9-]{36}$/);
  await graph.getByLabel('Named view', { exact: true }).selectOption(firstView);
  await expect(graph.locator('.diagram-node.process-card')).toHaveCount(60);
  const pageCDP = await context.newCDPSession(page); const graphCDP = await context.newCDPSession(graph); const browserCDP = await browser.newBrowserCDPSession();
  await pageCDP.send('Performance.enable'); await graphCDP.send('Performance.enable');
  const producer = spawn(python, [controller, 'produce', '--run-id', identifier, '--seconds', '1860'], { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  let producerOutput = ''; producer.stdout.on('data', data => { producerOutput += String(data); });
  let producerFailure = false; producer.on('error', () => { producerFailure = true; });
  const completed = new Promise<void>(fulfill => producer.on('exit', code => { producerFailure ||= code !== 0; fulfill(); }));
  const started = Date.now(); const observations: Record<string, unknown>[] = []; let lastReceived = 0; let cycles = 0;
  const artifact = resolve(output, `soak-${identifier}.json`);
  mkdirSync(output, { recursive: true }); mkdirSync(resolve(output, "screenshots"), { recursive: true });
  const report = { synthetic: true, project_id: project, run_id: identifier, configured_processes: 60, monitored_processes: 5, configured_total_appends_per_second: 1, requested_continuous_seconds: 1800, started_at_utc: new Date(started).toISOString(), finished_at_utc: null as string | null, actual_elapsed_seconds: 0, complete: false, observations, producer: null as unknown, errors: failures, external_requests: external, proxy: 'Direct fixture ASGI TLS; no proxy process is present, and OS/release qualification is not claimed.' };
  const persist = () => { report.actual_elapsed_seconds = (Date.now() - started) / 1000; writeFileSync(artifact, JSON.stringify(report, null, 2)); };
  async function sample(label: string) {
    const stateResponse = await page.request.get(`/api/v1/projects/${project}/live-sessions/${monitor!.session_id}?workspace_id=${monitor!.workspace_id}&lease_revision=${monitor!.lease_revision}`);
    expect(stateResponse.status()).toBe(200); const state = await stateResponse.json() as components['schemas']['LiveSessionResponse'];
    expect(state.status).toBe('following'); expect(state.process_ids).toHaveLength(5); expect(state.snapshot.sources).toHaveLength(5);
    const processInfo = await browserCDP.send('SystemInfo.getProcessInfo');
    const resources = await command(['resources', '--run-id', identifier]);
    observations.push({ label, elapsed_seconds: (Date.now() - started) / 1000, measured_at_utc: new Date().toISOString(), app_and_database: resources, browser_process_cpu: processInfo.processInfo, browser_process_memory: await hostBrowserProcesses(processInfo.processInfo.map(info => Number(info.id))), page_performance: (await pageCDP.send('Performance.getMetrics')).metrics, graph_performance: (await graphCDP.send('Performance.getMetrics')).metrics, websocket_connections_created: createdSockets, open_websocket_count: openSockets.size, live: { session_id: state.session_id, status: state.status, filter_version: state.filter_version, process_count: state.process_ids.length, counters: state.snapshot.counters, sources: state.snapshot.sources } });
    persist();
  }
  let stopFailure: unknown = null;
  try {
    await sample('start'); await page.screenshot({ path: resolve(output, `screenshots/soak-${identifier}-start-live.png`), animations: 'disabled' });
    while (Date.now() - started < duration) {
      await page.waitForTimeout(Math.min(30_000, duration - (Date.now() - started)));
      const selected = 5 + cycles % 55; const name = `Soak process ${String(selected).padStart(2, '0')}`;
      await graph.getByLabel('Search this system', { exact: true }).fill(name);
      await graph.locator('.search-results button').filter({ has: graph.getByText(name, { exact: true }) }).click();
      await expect(graph.getByRole('region', { name: 'Process details', exact: true })).toContainText(name);
      await graph.getByLabel('Search this system', { exact: true }).fill('');
      await graph.getByLabel('Named view', { exact: true }).selectOption(cycles % 2 ? firstView : secondView);
      await graph.getByRole('button', { name: 'Fit diagram', exact: true }).click();
      const term = ['SOAK', 'EVEN', 'ODD'][cycles % 3];
      const applying = page.waitForResponse(response => response.url().endsWith('/filters') && response.request().method() === 'PUT' && (response.request().postDataJSON() as { global_filter?: { include?: string[] } }).global_filter?.include?.[0] === term);
      await page.getByLabel('Live contains string', { exact: true }).fill(term); expect((await applying).status()).toBe(200);
      await expect(page.locator('.live-filter-state')).toHaveText(/^Applied version/);
      const received = Number(await page.getByTestId('live-received').innerText()); expect(received).toBeGreaterThan(lastReceived); lastReceived = received;
      expect(await page.getByTestId('live-session-id').innerText()).toBe(monitor!.session_id);
      expect(producerFailure).toBe(false); expect(failures).toEqual([]); expect(external).toEqual([]);
      cycles += 1;
      if (cycles % 5 === 0 || Date.now() - started >= duration) await sample(cycles % 30 === 0 ? 'midpoint-or-final' : 'periodic');
    }
    await sample('end');
    report.finished_at_utc = new Date().toISOString();
    expect((Date.now() - started) / 1000).toBeGreaterThanOrEqual(1800);
    expect(observations.length).toBeGreaterThanOrEqual(3); expect(openSockets.size).toBe(1);
    await graph.screenshot({ path: resolve(output, `screenshots/soak-${identifier}-end-sixty-processes.png`), animations: 'disabled' });
    await page.screenshot({ path: resolve(output, `screenshots/soak-${identifier}-end-live.png`), animations: 'disabled' });
    report.complete = true;
  } finally {
    try {
      await page.getByRole('button', { name: 'Stop this monitor', exact: true }).click();
      await expect(page.getByTestId('live-session-state')).toHaveText('stopped');
    } catch (error) { stopFailure = error; report.complete = false; }
    finally {
      await command(['stop', '--run-id', identifier]).catch(() => { producerFailure = true; });
      await Promise.race([completed, new Promise(fulfill => setTimeout(fulfill, 15000))]);
      if (producerOutput) { try { report.producer = JSON.parse(producerOutput); } catch { producerFailure = true; } }
      else producerFailure = true;
      if (producerFailure) report.complete = false;
      await graph.close().catch(() => {}); persist();
    }
  }
  if (stopFailure) throw stopFailure;
  expect(report.complete).toBe(true); expect(producerFailure).toBe(false);
  expect((report.producer as { exact_original_bytes_restored?: boolean })?.exact_original_bytes_restored).toBe(true);
  } finally {
    if (changed) {
      const current = await (await page.request.get(`/api/v1/projects/${project}/topology`)).json() as Topology;
      expect(current.revision).toBe(revision);
      const restoreConfig = structuredClone(original.config); restoreConfig.project.revision = current.revision;
      const restored = await page.request.put(`/api/v1/projects/${project}/topology`, { headers, data: { expected_revision: current.revision, config: restoreConfig, confirmed_deletions: true } });
      expect(restored.status()).toBe(200); const result = await restored.json() as Topology;
      await reapproveExisting(result.revision);
      const content = structuredClone(result.config); content.project.revision = original.config.project.revision;
      expect(content).toEqual(original.config);
      writeFileSync(resolve(snapshotDirectory, `${identifier}-restored.json`), JSON.stringify({ restored: true, original_revision: original.revision, restored_revision: result.revision, content_equal_except_revision: true }, null, 2));
    }
    await graph?.close().catch(() => {});
  }
});

test('restores the completed AT61 existing fixture snapshot with the current embedded revision', async ({ page, context, baseURL }) => {
  test.skip(process.env.INSPECTOR_E2E_SOAK_RESTORE_ONLY !== '1', 'Explicit recovery of a completed measured run only.');
  const measured = JSON.parse(readFileSync(resolve(output, `soak-${identifier}.json`), 'utf8')) as { complete: boolean; producer: { exact_original_bytes_restored: boolean } };
  expect(measured.complete).toBe(true); expect(measured.producer.exact_original_bytes_restored).toBe(true);
  await context.grantPermissions(['local-network-access'], { origin: baseURL! }); await serveBuiltAssets(context, baseURL!);
  const account = (JSON.parse(readFileSync(resolve(root, '.secrets/stage7-browser/accounts.json'), 'utf8')) as Record<string, { username: string; password: string }>).administrator;
  await page.goto('/'); await page.getByLabel('Username', { exact: true }).fill(account.username);
  try { await page.getByLabel('Password', { exact: true }).fill(account.password); expect((await submitSignIn(page)).status()).toBe(200); }
  catch { await page.locator('input[type="password"]').fill('').catch(() => {}); throw new Error('Existing synthetic recovery sign-in failed; protected values withheld.'); }
  const original = JSON.parse(readFileSync(resolve(root, `.state/stage7-soak/${identifier}-original.json`), 'utf8')) as Config;
  const current = await (await page.request.get(`/api/v1/projects/${project}/topology`)).json() as Topology;
  expect(current.revision).toBe(original.project.revision + 1); expect(current.config.processes).toHaveLength(60);
  expect(current.config.connections).toEqual(original.connections); expect(current.config.parsers).toEqual(original.parsers);
  const { csrf_token } = await (await page.request.get('/api/v1/auth/csrf')).json() as { csrf_token: string };
  const headers = { Origin: baseURL!, 'X-CSRF-Token': csrf_token }; const config = structuredClone(original); config.project.revision = current.revision;
  const response = await page.request.put(`/api/v1/projects/${project}/topology`, { headers, data: { expected_revision: current.revision, config, confirmed_deletions: true } });
  expect(response.status()).toBe(200); const restored = await response.json() as Topology;
  for (const connection of original.connections ?? []) {
    expect(connection.host).toBe('stage7-sftp'); expect(connection.port).toBe(8022); expect(connection.username).toBe(fixture!.username); expect(connection.allowed_log_roots).toEqual(['/var/log/inspector-demo']);
    const base = `/api/v1/projects/${project}/connections/${connection.id}/source-access`;
    const current = await (await page.request.get(base)).json() as components['schemas']['SourceAccessResponse']; expect(current.approval.revision).toBeGreaterThan(0); expect(current.roots).toEqual(['/var/log/inspector-demo']);
    const approved = await page.request.post(base + '/approve', { headers, data: { expected_config_revision: restored.revision, expected_approval_revision: current.approval.revision, verified: true } });
    expect(approved.status()).toBe(200); expect((await approved.json() as components['schemas']['SourceAccessResponse']).approval.approved).toBe(true);
  }
  const content = structuredClone(restored.config); content.project.revision = original.project.revision; expect(content).toEqual(original);
  writeFileSync(resolve(root, `.state/stage7-soak/${identifier}-restored.json`), JSON.stringify({ restored: true, original_revision: original.project.revision, restored_revision: restored.revision, content_equal_except_revision: true, recovery: 'Separate explicit completed-measurement cleanup retry with current embedded revision.' }, null, 2));
});
