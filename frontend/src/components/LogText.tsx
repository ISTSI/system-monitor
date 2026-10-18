import { Fragment, memo } from 'react';
import { logSegments, type HighlightFilter } from '../logHighlight';

type Props = { rawLine: string; timestampOriginal?: string | null; timestampUtc?: string | null; filters: readonly HighlightFilter[]; highlightLimitTitle?: string };

function LogText({ rawLine, timestampOriginal, timestampUtc, filters, highlightLimitTitle = 'Highlight limit reached; original text and filter results are unchanged.' }: Props) {
  const offset = timestampUtc && timestampOriginal && rawLine.startsWith(timestampOriginal) ? timestampOriginal.length : 0;
  const { segments, limited } = logSegments(rawLine, filters, offset);
  return <span data-highlight-limited={limited || undefined} title={limited ? highlightLimitTitle : undefined}>{segments.map(segment => segment.matched ? <mark className="literal-match" data-start={segment.start} data-end={segment.end} key={segment.start}>{segment.text}</mark> : <Fragment key={segment.start}>{segment.text}</Fragment>)}</span>;
}

export default memo(LogText);
