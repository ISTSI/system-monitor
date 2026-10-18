import { CASEFOLD } from './unicodeCasefold.ts';

export type HighlightFilter = { include?: readonly string[]; case_sensitive?: boolean };
export type HighlightContext = {
  filter?: HighlightFilter | null;
  global_filter?: HighlightFilter | null;
  per_process_filters?: Record<string, HighlightFilter> | null;
};
export type HighlightRange = { start: number; end: number };
export type LogSegment = HighlightRange & { text: string; matched: boolean };
export const MAX_HIGHLIGHT_UNITS = 65_536;
export const MAX_HIGHLIGHT_MARKS = 128;
const MAX_MATCHES = 512;

// Only acknowledged query/session state is passed here, never input drafts.
export function filtersForLog(context: HighlightContext | null | undefined, processId: string): HighlightFilter[] {
  if (!context) return [];
  return [context.filter ?? context.global_filter, context.per_process_filters?.[processId]].filter((filter): filter is HighlightFilter => !!filter);
}

export function casefold(value: string): string {
  return Array.from(value, char => CASEFOLD[char] ?? char).join('');
}

function foldOffsets(value: string): { text: string; starts: number[]; ends: number[] } {
  const chunks: string[] = []; const starts: number[] = []; const ends: number[] = [];
  let offset = 0;
  for (const char of value) {
    const folded = CASEFOLD[char] ?? char;
    chunks.push(folded);
    for (let index = 0; index < folded.length; index += 1) { starts.push(offset); ends.push(offset + char.length); }
    offset += char.length;
  }
  return { text: chunks.join(''), starts, ends };
}

export function highlightRanges(raw: string, filters: readonly HighlightFilter[]): { ranges: HighlightRange[]; limited: boolean } {
  const active = filters.filter(filter => filter.include?.some(term => term !== ''));
  if (!active.length) return { ranges: [], limited: false };
  const text = raw.slice(0, MAX_HIGHLIGHT_UNITS);
  let folded: ReturnType<typeof foldOffsets> | null = null;
  const found: HighlightRange[] = []; let attempts = 0; let limited = raw.length > text.length;
  outer: for (const filter of active.slice(0, 2)) {
    const sensitive = filter.case_sensitive !== false;
    if (!sensitive && !folded) folded = foldOffsets(text);
    const haystack = sensitive ? text : folded!.text;
    for (const term of (filter.include ?? []).slice(0, 20)) {
      if (term === '' || Array.from(term).length > 512) continue;
      const needle = sensitive ? term : casefold(term);
      let from = 0;
      while (from <= haystack.length) {
        const index = haystack.indexOf(needle, from);
        if (index < 0) break;
        if (attempts++ >= MAX_MATCHES) { limited = true; break outer; }
        found.push(sensitive ? { start: index, end: index + needle.length } : { start: folded!.starts[index], end: folded!.ends[index + needle.length - 1] });
        from = index + 1;
      }
    }
  }
  found.sort((left, right) => left.start - right.start || left.end - right.end);
  const ranges: HighlightRange[] = [];
  for (const item of found) {
    const previous = ranges.at(-1);
    if (previous && item.start <= previous.end) previous.end = Math.max(previous.end, item.end);
    else if (ranges.length < MAX_HIGHLIGHT_MARKS) ranges.push({ ...item });
    else { limited = true; break; }
  }
  return { ranges, limited };
}

export function logSegments(raw: string, filters: readonly HighlightFilter[], visibleOffset = 0): { segments: LogSegment[]; limited: boolean } {
  const offset = Math.min(raw.length, Math.max(0, visibleOffset));
  const { ranges, limited } = highlightRanges(raw, filters);
  const segments: LogSegment[] = []; let position = offset;
  for (const range of ranges) {
    const start = Math.max(offset, range.start); const end = range.end;
    if (end <= start) continue;
    if (start > position) segments.push({ start: position, end: start, text: raw.slice(position, start), matched: false });
    segments.push({ start, end, text: raw.slice(start, end), matched: true }); position = end;
  }
  if (position < raw.length) segments.push({ start: position, end: raw.length, text: raw.slice(position), matched: false });
  return { segments, limited };
}
