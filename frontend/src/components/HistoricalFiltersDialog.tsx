import { useState } from 'react';
import type { HistoricalQuery } from '../investigation';
import { useI18n } from '../i18n';
import { utc } from '../utcDateTime';
import { ErrorNotice, Modal } from './Common';
import UtcDateTimeInput from './UtcDateTimeInput';

export type HistoricalFilterDraft = {
  from: string;
  to: string;
  filter: HistoricalQuery['filter'];
  per_process_filters: NonNullable<HistoricalQuery['per_process_filters']>;
};

type Filter = NonNullable<HistoricalQuery['filter']>;
type ProcessOption = { id: string; name: string; host: string };
type Draft = Omit<HistoricalFilterDraft, 'filter'> & { filter: Filter };

function copyFilter(filter?: Filter): Filter {
  return { include: [...(filter?.include ?? [])], exclude: [...(filter?.exclude ?? [])],
    include_mode: filter?.include_mode ?? 'all', case_sensitive: filter?.case_sensitive ?? true };
}

function copyDraft(initial: HistoricalFilterDraft): Draft {
  return { from: initial.from, to: initial.to, filter: copyFilter(initial.filter),
    per_process_filters: Object.fromEntries(Object.entries(initial.per_process_filters).map(([id, filter]) => [id, copyFilter(filter)])) };
}

export default function HistoricalFiltersDialog({ initial, processOptions, bounds, busy, error, onApply, onClose }: {
  initial: HistoricalFilterDraft;
  processOptions: ProcessOption[];
  bounds?: { from: string; to: string };
  busy: boolean;
  error: string;
  onApply: (draft: HistoricalFilterDraft) => Promise<boolean>;
  onClose: () => void;
}) {
  const { t } = useI18n();
  // The dialog owns its draft. Closing it never changes the table's query.
  const [draft, setDraft] = useState(() => copyDraft(initial));
  const [scope, setScope] = useState('');
  const [action, setAction] = useState<'include' | 'exclude'>('include');
  const [content, setContent] = useState('');
  const [validationError, setValidationError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const disabled = busy || submitting;
  const processes = new Map(processOptions.map(process => [process.id, process]));
  const processLabel = (id: string) => {
    const process = processes.get(id);
    return process ? `${process.host}: ${process.name}` : t('Unavailable process');
  };
  const scopeLabel = (id: string) => id ? processLabel(id) : t('All processes');
  const scopeFilter = scope ? draft.per_process_filters[scope] ?? {
    include: [], exclude: [], include_mode: draft.filter.include_mode, case_sensitive: draft.filter.case_sensitive,
  } : draft.filter;

  function updateFilter(id: string, change: (filter: Filter) => Filter) {
    setValidationError('');
    setDraft(current => {
      if (!id) return { ...current, filter: change(current.filter) };
      const existing = current.per_process_filters[id] ?? {
        include: [], exclude: [], include_mode: current.filter.include_mode, case_sensitive: current.filter.case_sensitive,
      };
      return { ...current, per_process_filters: { ...current.per_process_filters, [id]: change(existing) } };
    });
  }

  function addFilter() {
    if (!content.length || Array.from(content).length > 512) {
      setValidationError('Enter log content of 1–512 Unicode characters.'); return;
    }
    if ((scopeFilter[action]?.length ?? 0) >= 20) {
      setValidationError('Each scope allows at most 20 include and 20 exclude filters.'); return;
    }
    const term = content;
    updateFilter(scope, filter => ({ ...filter, [action]: [...(filter[action] ?? []), term] }));
    setContent('');
  }

  async function applyFilters() {
    setValidationError('');
    let from: string; let to: string;
    try {
      from = utc(draft.from); to = utc(draft.to);
      if (from >= to) throw new Error('The exclusive end must follow the inclusive start.');
      for (const filter of [draft.filter, ...Object.values(draft.per_process_filters)]) {
        if ((filter.include?.length ?? 0) > 20 || (filter.exclude?.length ?? 0) > 20) {
          throw new Error('Each scope allows at most 20 include and 20 exclude filters.');
        }
        if ([...(filter.include ?? []), ...(filter.exclude ?? [])].some(term => Array.from(term).length > 512)) {
          throw new Error('Each log content filter allows at most 512 Unicode characters.');
        }
      }
    } catch (cause) {
      setValidationError(cause instanceof Error ? cause.message : 'The filters are invalid.'); return;
    }
    setSubmitting(true);
    try {
      const applied = await onApply({ ...draft, from, to });
      setSubmitting(false);
      if (applied) onClose();
    } catch (cause) {
      setSubmitting(false);
      setValidationError(cause instanceof Error ? cause.message : 'The filters could not be applied.');
    }
  }

  const groups = [{ id: '', filter: draft.filter }, ...Object.entries(draft.per_process_filters).map(([id, filter]) => ({ id, filter }))];
  const filterCount = groups.reduce((total, group) => total + (group.filter.include?.length ?? 0) + (group.filter.exclude?.length ?? 0), 0);
  return <Modal title={t('Filters')} onClose={() => { if (!disabled) onClose(); }}>
    <p className="muted">{t('Filter the logs already collected. These settings do not change the collection range or start collection.')}</p>
    {(validationError || error) && <ErrorNotice>{t(validationError || error)}</ErrorNotice>}
    <fieldset className="history-filter-fields" disabled={disabled}>
      <legend>{t('Display time range')}</legend>
      <div className="form-grid">
        <UtcDateTimeInput bound="From" value={draft.from} onChange={from => { setDraft(current => ({ ...current, from })); setValidationError(''); }} />
        <UtcDateTimeInput bound="To" value={draft.to} onChange={to => { setDraft(current => ({ ...current, to })); setValidationError(''); }} />
      </div>
      <p className="muted">{t('All values are in UTC. The start is inclusive and the end is exclusive.')}</p>
      {bounds && <button type="button" onClick={() => { setDraft(current => ({ ...current, from: bounds.from, to: bounds.to })); setValidationError(''); }}>{t('Reset time range')}</button>}
    </fieldset>
    <fieldset className="history-filter-fields" disabled={disabled}>
      <legend>{t('Existing filters')}</legend>
      {filterCount ? <ul className="history-filter-list">{groups.flatMap(({ id, filter }) => (['include', 'exclude'] as const).flatMap(kind => (filter[kind] ?? []).map((term, index) => <li key={`${id}:${kind}:${index}`}>
        <span title={id || undefined}>{scopeLabel(id)}</span><strong>{t(kind === 'include' ? 'Include' : 'Exclude')}</strong><code>{term}</code>
        <button type="button" aria-label={t('Remove {kind} filter {index} for {scope}', { kind: t(kind === 'include' ? 'include' : 'exclude'), index: index + 1, scope: scopeLabel(id) })} onClick={() => updateFilter(id, current => ({ ...current, [kind]: current[kind]?.filter((_, position) => position !== index) ?? [] }))}>{t('Remove filter')}</button>
      </li>)))}</ul> : <p className="muted">{t('No log content filters.')}</p>}
      <button type="button" disabled={disabled || !filterCount} onClick={() => { setDraft(current => ({ ...current, filter: { ...current.filter, include: [], exclude: [] }, per_process_filters: {} })); setValidationError(''); }}>{t('Clear content filters')}</button>
    </fieldset>
    <fieldset className="history-filter-fields" disabled={disabled}>
      <legend>{t('Add a filter')}</legend>
      <form onSubmit={event => { event.preventDefault(); addFilter(); }}>
        <div className="form-grid">
          <label>{t('Log content')}<input aria-label={t('Log content')} value={content} spellCheck={false} onChange={event => { setContent(event.target.value); setValidationError(''); }} /></label>
          <label>{t('Filter action')}<select aria-label={t('Filter action')} value={action} onChange={event => setAction(event.target.value as 'include' | 'exclude')}><option value="include">{t('Include')}</option><option value="exclude">{t('Exclude')}</option></select></label>
          <label>{t('Filter scope')}<select aria-label={t('Filter scope')} value={scope} onChange={event => setScope(event.target.value)}><option value="">{t('All processes')}</option>{processOptions.map(process => <option key={process.id} value={process.id} title={process.id}>{process.host}: {process.name}</option>)}</select></label>
        </div>
        <button type="submit">{t('Add filter')}</button>
      </form>
      <div className="form-grid">
        <label>{t('Global include matching')}<select aria-label={t('Global include matching')} value={draft.filter.include_mode} onChange={event => updateFilter('', filter => ({ ...filter, include_mode: event.target.value as 'any' | 'all' }))}><option value="all">{t('All include terms')}</option><option value="any">{t('Any include term')}</option></select></label>
        <label className="checkbox-label"><input type="checkbox" checked={draft.filter.case_sensitive} onChange={event => updateFilter('', filter => ({ ...filter, case_sensitive: event.target.checked }))} />{t('Global case sensitive')}</label>
      </div>
      {!!scope && <details><summary title={scope}>{t('Per-process matching')} · {scopeLabel(scope)}</summary><div className="form-grid">
        <label>{t('Process include matching')}<select aria-label={t('Process include matching')} value={scopeFilter.include_mode} onChange={event => updateFilter(scope, filter => ({ ...filter, include_mode: event.target.value as 'any' | 'all' }))}><option value="all">{t('All include terms')}</option><option value="any">{t('Any include term')}</option></select></label>
        <label className="checkbox-label"><input type="checkbox" checked={scopeFilter.case_sensitive} onChange={event => updateFilter(scope, filter => ({ ...filter, case_sensitive: event.target.checked }))} />{t('Process case sensitive')}</label>
      </div></details>}
    </fieldset>
    <div className="form-actions"><button type="button" disabled={disabled} onClick={onClose}>{t('Cancel')}</button><button type="button" className="primary" disabled={disabled} onClick={() => { void applyFilters(); }}>{t('Apply filters')}</button></div>
  </Modal>;
}
