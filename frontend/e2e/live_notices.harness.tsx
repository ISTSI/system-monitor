// TEST-ONLY: real LiveViewer, synthetic configuration, intercepted HTTP and WS.
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import LiveViewer from '../src/components/LiveViewer';
import { VirtualLog } from '../src/components/HistoricalLogTable';
import { I18nProvider } from '../src/i18n';
import type { HistoricalEvent } from '../src/investigation';
import type { Config } from '../src/topology';
import '../src/theme/tokens.css';
import '../src/styles.css';

const config: Config = {
  schema_version: '2.0',
  project: { id: 'test-only-project', name: 'Synthetic test system', description: '', revision: 1, display_timezone: 'UTC' },
  subsystems: [], flows: [], views: [],
  servers: [
    { id: 'server-internal-one', name: 'server-one', subsystem_id: 'subsystem-one', description: '', tags: [] },
    { id: 'server-internal-two', name: 'server-two', subsystem_id: 'subsystem-two', description: '', tags: [] },
  ],
  processes: [
    { id: 'process-internal-one', name: 'worker-one', server_id: 'server-internal-one', description: '', tags: [], pcs_resource_name: null },
    { id: 'process-internal-two', name: 'worker-two', server_id: 'server-internal-two', description: '', tags: [], pcs_resource_name: null },
  ],
};
const selection = { ids: [], version: 0 };
const referenceEvents: HistoricalEvent[] = [{
  schema_version: '1.0', project_id: config.project.id, event_id: 'historical-reference', process_id: config.processes[0].id,
  server_id: config.servers[0].id, process_name_snapshot: config.processes[0].name, server_name_snapshot: config.servers[0].name,
  raw_line: '2026-10-18T10:00:00Z historical presentation reference', timestamp_original: '2026-10-18T10:00:00Z',
  timestamp_utc: '2026-10-18T10:00:00.000000Z', timestamp_us: null, received_at: '2026-10-18T10:00:01.000000Z', parse_status: 'parsed', metadata: {},
  source: { source_revision_id: 'reference-source', remote_path: '/test-only/reference.log', archive_member: null, member_ordinal: null, byte_start: 0, byte_end: 55, line_number: 1, content_sha256: 'a'.repeat(64) },
}];

function Harness() {
  const [live, setLive] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [workspaceId] = useState(() => crypto.randomUUID());
  return <I18nProvider language="en"><main style={{ padding: 16 }}>
    <p role="note">TEST-ONLY synthetic fixture. No backend or SSH connection.</p>
    <nav className="workspace-tabs" aria-label="Test workspace sections">
      <button className={!live ? 'active' : ''} onClick={() => setLive(false)}>Topology</button>
      <button className={live ? 'active' : ''} onClick={() => setLive(true)}>Live monitor</button>
      <button onClick={() => { document.documentElement.dataset.theme = 'light'; }}>Light test theme</button>
      <button onClick={() => { document.documentElement.dataset.theme = 'dark'; }}>Dark test theme</button>
    </nav>
    <p role="status">{capturing ? 'Test page capture active' : 'Test page capture inactive'}</p>
    {!live && <p>Topology test placeholder.</p>}
    <div hidden={!live}><LiveViewer projectId={config.project.id} config={config} workspaceId={workspaceId} selection={selection} archived={false} visible={live} onCaptureChange={setCapturing} onOpenRecording={() => { throw new Error('Unexpected recording navigation in test-only harness.'); }} /></div>
    {new URLSearchParams(location.search).has('reference') && <section aria-label="Historical presentation reference">
      <h2>TEST-ONLY historical presentation reference</h2>
      <VirtualLog events={referenceEvents} label="Historical presentation reference" columns={{ timestamp: true, process: true, host: true }} highlights={null} onInspect={() => { throw new Error('Unexpected context action in presentation reference.'); }} />
    </section>}
  </main></I18nProvider>;
}

createRoot(document.getElementById('root')!).render(<Harness />);
