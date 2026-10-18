// TEST-ONLY source-component browser fixture. No API, credentials or SSH.
import { expect, test, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { createServer, type ViteDevServer } from 'vite';
import react from '@vitejs/plugin-react';
import type { Config, Geometry } from '../src/topology';

const origin = 'http://127.0.0.1:5193';
const config: Config = {
  schema_version: '2.0', project: { id: 'test-only-grid', name: 'Synthetic grid test', description: '', revision: 1, display_timezone: 'UTC' },
  subsystems: [{ id: 'outer', name: 'Outer group', description: '', tags: [] }],
  servers: [{ id: 'server', name: 'Nested server', subsystem_id: 'outer', description: '', tags: [] }],
  processes: ['one', 'two'].map(id => ({ id, name: id, server_id: 'server', description: '', tags: [], pcs_resource_name: null })),
  flows: [], views: [{ id: 'view', name: 'Synthetic layout', flow_ids: [], nodes: [
    { element_id: 'outer', x: 13, y: 19, width: 1000, height: 800, collapsed: false },
    { element_id: 'server', x: 33, y: 61, width: 800, height: 650, collapsed: false },
    { element_id: 'one', x: 31, y: 75, width: 300, height: 72, collapsed: false },
    { element_id: 'two', x: 31, y: 211, width: 300, height: 72, collapsed: false },
  ] }],
};
const harness = `
import { useCallback, useState } from 'react';
import { createRoot } from 'react-dom/client';
import TopologyGraph from '/src/components/TopologyGraph';
import { I18nProvider } from '/src/i18n';
import '/src/theme/tokens.css';
import '/src/styles.css';
const config = ${JSON.stringify(config)};
const key = 'TEST-ONLY-topology-grid-geometry';
const highlighted = new Set();
const none = () => {};
function Harness() {
  const [view, setView] = useState(() => JSON.parse(sessionStorage.getItem(key) || 'null') || config.views[0]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [writes, setWrites] = useState(0);
  const select = useCallback((selection, additive) => setSelectedIds(current => additive ? [...new Set([...current, selection.id])] : [selection.id]), []);
  const save = useCallback((id, geometry, moved = []) => {
    setView(current => {
      const next = structuredClone(current);
      Object.assign(next.nodes.find(node => node.element_id === id), geometry);
      moved.forEach(item => Object.assign(next.nodes.find(node => node.element_id === item.id), item.position));
      sessionStorage.setItem(key, JSON.stringify(next));
      return next;
    });
    setWrites(current => current + 1);
  }, []);
  return <I18nProvider language="en"><main style={{ width: '100vw', height: 950, display: 'flex', flexDirection: 'column' }}>
    <p>TEST-ONLY synthetic topology. Saving records the real graph callback locally; no backend or SSH.</p>
    <output data-testid="geometry" style={{ display: 'none' }}>{JSON.stringify(view.nodes)}</output>
    <output data-testid="writes">{writes}</output>
    <TopologyGraph config={config} view={view} editable={!location.search.includes('inspector')} selection={null} selectedIds={selectedIds} highlighted={highlighted} reveal={0} saving={false} onSelect={select} onMultiSelect={setSelectedIds} onGeometry={save} onCollapse={none} onConnect={none} onAddChild={none} />
  </main></I18nProvider>;
}
createRoot(document.getElementById('root')).render(<Harness />);
`;
let server: ViteDevServer;
test.beforeAll(async () => {
  const id = resolve('e2e/__test-only-topology-grid-harness.tsx').replaceAll('\\', '/');
  server = await createServer({
    configFile: false, root: resolve('.'), plugins: [{
      name: 'test-only-topology-grid-fixture',
      resolveId(source) { if (source === '/__topology-grid-harness.tsx') return id; },
      load(source) { if (source === id) return harness; },
      configureServer(vite) {
        vite.middlewares.use('/__topology-grid.html', async (_request, response) => {
          response.setHeader('Content-Type', 'text/html');
          response.end(await vite.transformIndexHtml('/__topology-grid.html', '<!doctype html><html data-theme="light"><head><title>TEST-ONLY topology grid</title></head><body><div id="root"></div><script type="module" src="/__topology-grid-harness.tsx"></script></body></html>'));
        });
      },
    }, react()],
    server: { host: '127.0.0.1', port: 5193, strictPort: true, hmr: false },
  });
  await server.listen();
});
test.afterAll(async () => { await server?.close(); });
test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
});

async function geometry(page: Page): Promise<Geometry[]> {
  return JSON.parse((await page.getByTestId('geometry').textContent())!) as Geometry[];
}
async function drag(page: Page, id: string, dx: number, dy: number) {
  const node = page.getByTestId(`rf__node-${id}`);
  const box = await node.boundingBox(); expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + 18);
  await page.mouse.down(); await page.mouse.move(box!.x + box!.width / 2 + dx, box!.y + 18 + dy, { steps: 8 }); await page.mouse.up();
}
function absolute(nodes: Geometry[], id: string): { x: number; y: number } {
  const node = nodes.find(node => node.element_id === id)!;
  const parent = id === 'server' ? 'outer' : id === 'one' || id === 'two' ? 'server' : undefined;
  const offset = parent ? absolute(nodes, parent) : { x: 0, y: 0 };
  return { x: node.x + offset.x, y: node.y + offset.y };
}
function expectAligned(nodes: Geometry[], ids: string[]) {
  for (const id of ids) {
    const point = absolute(nodes, id);
    expect(Math.abs(point.x % 8), `${id} canvas x`).toBe(0); expect(Math.abs(point.y % 8), `${id} canvas y`).toBe(0);
  }
}

test('dragging nested elements snaps their saved canvas positions, including boundaries and a multiple selection', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${origin}/__topology-grid.html`);
  await expect(page.getByTestId('rf__node-one')).toBeVisible();
  await expect(page.getByTestId('writes')).toHaveText('0');
  expect(await geometry(page)).toEqual(config.views[0].nodes);
  await expect(page.locator('.react-flow__background')).toHaveCount(0);
  await drag(page, 'one', 37, 23);
  await expect(page.getByTestId('writes')).toHaveText('1');
  let saved = await geometry(page); expectAligned(saved, ['one']);
  expect(saved.find(node => node.element_id === 'outer')).toEqual(config.views[0].nodes[0]);
  expect(saved.find(node => node.element_id === 'server')).toEqual(config.views[0].nodes[1]);
  expect(saved.find(node => node.element_id === 'two')).toEqual(config.views[0].nodes[3]);
  await page.reload(); await expect(page.getByTestId('rf__node-one')).toBeVisible();
  expect(await geometry(page)).toEqual(saved); await expect(page.getByTestId('writes')).toHaveText('0');
  await drag(page, 'one', -1000, -1000);
  await expect(page.getByTestId('writes')).toHaveText('1');
  saved = await geometry(page); expectAligned(saved, ['one']);
  expect(saved.find(node => node.element_id === 'one')!.x).toBeGreaterThanOrEqual(10);
  expect(saved.find(node => node.element_id === 'one')!.y).toBeGreaterThanOrEqual(50);
  await page.getByRole('button', { name: 'Select process one', exact: true }).click();
  await page.getByRole('button', { name: 'Select process two', exact: true }).click({ modifiers: ['Control'] });
  await expect(page.locator('.react-flow__node.selected')).toHaveCount(2);
  await drag(page, 'one', 41, 29);
  await expect(page.getByTestId('writes')).toHaveText('2');
  saved = await geometry(page); expectAligned(saved, ['one', 'two']);
  expect(absolute(saved, 'two').x).not.toEqual(absolute(config.views[0].nodes, 'two').x);
  await page.getByRole('button', { name: 'Select server Nested server', exact: true }).click();
  await drag(page, 'server', 31, 19);
  await expect(page.getByTestId('writes')).toHaveText('3');
  const afterServer = await geometry(page); expectAligned(afterServer, ['server']);
  expect(afterServer.filter(node => ['one', 'two'].includes(node.element_id))).toEqual(saved.filter(node => ['one', 'two'].includes(node.element_id)));
  await page.getByRole('button', { name: 'Select subsystem Outer group', exact: true }).click();
  await drag(page, 'outer', -23, 17);
  await expect(page.getByTestId('writes')).toHaveText('4');
  expectAligned(await geometry(page), ['outer']);
  const evidence = resolve('../verification/topology-grid'); mkdirSync(evidence, { recursive: true });
  for (const theme of ['light', 'dark']) {
    await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
    await page.screenshot({ path: resolve(evidence, `${theme}.png`), animations: 'disabled' });
  }
  expect(errors).toEqual([]);
});

test('keyboard movement saves snapped positions and read-only diagrams cannot move elements', async ({ page }) => {
  await page.goto(`${origin}/__topology-grid.html`);
  await page.getByRole('button', { name: 'Select process one', exact: true }).click();
  await page.getByTestId('rf__node-one').focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByTestId('writes')).toHaveText('1');
  expectAligned(await geometry(page), ['one']);
  await page.goto(`${origin}/__topology-grid.html?inspector`);
  await expect(page.getByTestId('rf__node-one')).toBeVisible();
  const before = await geometry(page);
  await drag(page, 'one', 45, 25);
  await page.getByTestId('rf__node-one').focus(); await page.keyboard.press('ArrowRight');
  await expect(page.getByTestId('writes')).toHaveText('0'); expect(await geometry(page)).toEqual(before);
});
