import { useI18n } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { message, write } from '../api/client';
import type { components } from '../api/schema';
import type { Config, Parser } from '../topology';
import { ErrorNotice } from './Common';
import './parser-test.css';

type Result = components['schemas']['ParserTestResponse'];

export default function ParserTestPanel({ config, draftVersion, getParser }: { config: Config; draftVersion: number; getParser: () => Parser }) {
  const { t } = useI18n();
  const [sample, setSample] = useState('2026-10-16T12:00:00.123456Z INFO request_id=REQ-0042 example\ncontinuation without a timestamp');
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const fileGeneration = useRef(0);
  useEffect(() => { generation.current += 1; setResult(null); }, [sample, draftVersion, config.project.id, config.project.revision]);
  useEffect(() => () => { generation.current += 1; fileGeneration.current += 1; }, []);
  async function testSample() {
    fileGeneration.current += 1;
    const version = ++generation.current; setError(''); setResult(null); setBusy(true);
    try {
      if (new TextEncoder().encode(sample).length > 65536) throw new Error('Use a sample of at most 64 KiB.');
      const value = await write<Result>(`/projects/${encodeURIComponent(config.project.id)}/parsers/test`, { project_id: config.project.id, expected_revision: config.project.revision, parser: getParser(), sample });
      if (generation.current === version && value.project_id === config.project.id && value.revision === config.project.revision) setResult(value);
    } catch (cause) { if (generation.current === version) setError(message(cause)); }
    finally { setBusy(false); }
  }
  return <section className="parser-test" aria-label={t("Parser sample test")}>
    <h3>{t("Test parser draft")}</h3>
    <p className="field-help">{t("Paste anonymised UTF-8 text or choose a small file. The collection parser tests up to 100 physical lines, each at most 4 KiB; total 64 KiB. Results use UTC. Samples are not saved.")}</p>
    <label>{t("Parser sample")}<textarea aria-label={t("Parser sample")} rows={4} maxLength={65536} value={sample} onChange={event => { fileGeneration.current += 1; setSample(event.target.value); }} spellCheck={false} /></label>
    <label>{t("Upload parser sample")}<input aria-label={t("Upload parser sample")} type="file" accept=".txt,.log,text/plain" disabled={busy} onChange={event => {
      const file = event.target.files?.[0]; if (!file) return;
      const version = ++fileGeneration.current;
      setError(''); setResult(null);
      if (file.size > 65536) { setError('Use a sample of at most 64 KiB.'); event.target.value = ''; return; }
      void file.arrayBuffer().then(bytes => { if (fileGeneration.current === version) setSample(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes)); }).catch(() => { if (fileGeneration.current === version) setError('The sample must be valid UTF-8 text.'); });
    }} /></label>
    <button type="button" disabled={busy || !sample} onClick={() => { void testSample(); }}>{busy ? t("Testing parser…") : t("Test parser sample")}</button>
    {error && <ErrorNotice>{t(error)}</ErrorNotice>}
    {result && <div role="status"><p><strong>{result.valid_count} {t("valid timestamps ·")} {result.error_count} {t("parse errors")}</strong> · {config.project.name} {t("· revision")} {result.revision}</p>
      <div className="parser-results" tabIndex={0} role="region" aria-label={t("Parser sample results")}><table><thead><tr><th scope="col">{t("Line / original text")}</th><th scope="col">{t("Original timestamp")}</th><th scope="col">{t("UTC / exact microseconds")}</th><th scope="col">{t("Extracted fields / errors")}</th></tr></thead><tbody>{result.lines.map(line => <tr key={line.line_number}><td><span>{t("Line")} {line.line_number}</span><pre>{line.original_line}</pre></td><td><code>{line.timestamp_original ?? t("Not extracted")}</code></td><td><code>{line.timestamp_utc ?? t("Unknown timestamp")}</code>{line.timestamp_us !== null && <small>{line.timestamp_us} {t("µs since epoch")}</small>}</td><td>{line.error && <p className="history-warning">{line.error}</p>}{Object.entries(line.metadata).map(([key, value]) => <div key={key}><strong>{key}</strong>: <code>{value}</code></div>)}{!Object.keys(line.metadata).length && <span>{t("No configured fields found.")}</span>}</td></tr>)}</tbody></table></div>
      <p className="field-help">{t("Only configured literal correlation markers are extracted. A level appears when a marker for it is configured. Unknown timestamps remain in the diagnostic lane.")}</p>
    </div>}
  </section>;
}
