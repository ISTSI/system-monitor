import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { casefold, filtersForLog, highlightRanges, logSegments, MAX_HIGHLIGHT_MARKS } from '../src/logHighlight.ts';

const sensitive = (...include) => [{ include, case_sensitive: true }];
const folded = (...include) => [{ include, case_sensitive: false }];
const matched = result => result.segments.filter(segment => segment.matched);

test('casefold agrees for German expansions, Greek sigma and Turkish non-locale forms', () => {
  assert.equal(casefold('Straße ẞ Σςσ İIı'), 'strasse ss σσσ i\u0307iı');
  assert.deepEqual(highlightRanges('Straße', folded('STRASSE')).ranges, [{ start: 0, end: 6 }]);
  assert.deepEqual(highlightRanges('Σςσ', folded('σσσ')).ranges, [{ start: 0, end: 3 }]);
  assert.deepEqual(highlightRanges('İ I ı', folded('i')).ranges, [{ start: 0, end: 1 }, { start: 2, end: 3 }]);
  assert.deepEqual(highlightRanges('İ I ı', folded('ı')).ranges, [{ start: 4, end: 5 }]);
});

test('case-sensitive literal matching does not interpret regex, SQL, HTML or shell punctuation', () => {
  for (const term of ['.*[x]', '%_LIKE', '<script>', '$(whoami)', 'a\\b', 'a|b']) {
    const raw = `before ${term} after`;
    assert.deepEqual(matched(logSegments(raw, sensitive(term))).map(segment => segment.text), [term]);
  }
  assert.deepEqual(highlightRanges('Straße', sensitive('STRASSE')).ranges, []);
});

test('overlapping, adjacent and repeated terms merge without changing source text', () => {
  const raw = 'ababa ababa';
  const result = logSegments(raw, sensitive('aba', 'bab', 'aba'));
  assert.deepEqual(matched(result).map(segment => [segment.start, segment.end]), [[0, 5], [6, 11]]);
  assert.equal(result.segments.map(segment => segment.text).join(''), raw);
  assert.equal(logSegments('hello', sensitive('hello', 'ell')).segments.length, 1);
});

test('UTF-16 source offsets preserve astral characters and casefold expansions', () => {
  const raw = '😀 Straẞe 𐐀';
  const result = logSegments(raw, folded('😀', 'STRASSE', '𐐨'));
  assert.deepEqual(matched(result).map(segment => [segment.text, segment.start, segment.end]), [['😀', 0, 2], ['Straẞe', 3, 9], ['𐐀', 10, 12]]);
  assert.equal(result.segments.map(segment => segment.text).join(''), raw);
  for (const segment of result.segments) assert.equal(raw.slice(segment.start, segment.end), segment.text);
});

test('hidden timestamps remain in matching semantics and offsets refer to original raw text', () => {
  const raw = '2026-10-16T12:00:00Z INFO Straße'; const offset = raw.indexOf(' INFO');
  const result = logSegments(raw, folded('STRASSE'), offset);
  assert.equal(result.segments.map(segment => segment.text).join(''), raw.slice(offset));
  assert.deepEqual(matched(result).map(segment => [segment.text, segment.start, segment.end]), [['Straße', 26, 32]]);
  assert.equal(matched(logSegments(raw, sensitive('2026-10-16'), offset)).length, 0);
  assert.equal(matched(logSegments(raw, sensitive('00Z INFO'), offset))[0].text, ' INFO');
});

test('historical applied queries and acknowledged live sessions use global plus owning process filters', () => {
  const filters = { include: ['global'], case_sensitive: true };
  const perProcess = { first: { include: ['Straße'], case_sensitive: false }, foreign: { include: ['secret'], case_sensitive: true } };
  const historical = { filter: filters, per_process_filters: perProcess };
  const live = { global_filter: filters, per_process_filters: perProcess };
  for (const applied of [historical, live]) {
    assert.deepEqual(matched(logSegments('global STRASSE secret', filtersForLog(applied, 'first'))).map(segment => segment.text), ['global', 'STRASSE']);
    assert.deepEqual(matched(logSegments('global STRASSE secret', filtersForLog(applied, 'other'))).map(segment => segment.text), ['global']);
  }
  assert.deepEqual(filtersForLog(null, 'first'), []);
});

test('draft edits do not mutate acknowledged filters; clearing removes highlights', () => {
  const acknowledged = { global_filter: { include: ['old'], case_sensitive: true }, per_process_filters: {} };
  const draft = { ...acknowledged, global_filter: { include: ['new'], case_sensitive: true } };
  assert.equal(matched(logSegments('old new', filtersForLog(acknowledged, 'one')))[0].text, 'old');
  assert.equal(matched(logSegments('old new', filtersForLog(draft, 'one')))[0].text, 'new');
  assert.equal(matched(logSegments('old new', filtersForLog({ global_filter: { include: [], case_sensitive: true } }, 'one'))).length, 0);
  assert.equal(matched(logSegments('old new', [{ include: [''], case_sensitive: true }])).length, 0);
});

test('highlight limits cap DOM segments but preserve every original character', () => {
  const raw = 'x '.repeat(1000) + 'tail'; const result = logSegments(raw, sensitive('x'));
  assert.equal(result.limited, true); assert.ok(matched(result).length <= MAX_HIGHLIGHT_MARKS);
  assert.ok(result.segments.length <= MAX_HIGHLIGHT_MARKS * 2 + 1);
  assert.equal(result.segments.map(segment => segment.text).join(''), raw);
  const huge = 'a'.repeat(70_000) + 'b'; const bounded = logSegments(huge, sensitive('b'));
  assert.equal(bounded.limited, true); assert.equal(bounded.segments.map(segment => segment.text).join(''), huge);
});

// Compile only the local known React component, without loading a browser or
// introducing a test framework/dependency. The pure TS helper uses Node's types
// stripping; the same component is mounted by both actual virtual log viewers.
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(frontend, '..'); mkdirSync(resolve(root, '.state'), { recursive: true });
const directory = mkdtempSync(resolve(root, '.state/log-highlight-test-'));
const component = ts.transpileModule(readFileSync(resolve(frontend, 'src/components/LogText.tsx'), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2023, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX } }).outputText
  .replaceAll('"react/jsx-runtime"', JSON.stringify(pathToFileURL(resolve(frontend, 'node_modules/react/jsx-runtime.js')).href))
  .replaceAll("'react'", JSON.stringify(pathToFileURL(resolve(frontend, 'node_modules/react/index.js')).href))
  .replaceAll("'../logHighlight'", JSON.stringify(pathToFileURL(resolve(frontend, 'src/logHighlight.ts')).href));
const modulePath = resolve(directory, 'LogText.mjs'); writeFileSync(modulePath, component);
const { default: LogText } = await import(pathToFileURL(modulePath).href);

test('actual React log text renders escaped text nodes and semantic marks with raw offsets', () => {
  const raw = '2026-10-16T12:00:00Z <script>x</script> Straße';
  const rendered = renderToStaticMarkup(createElement(LogText, { rawLine: raw, timestampUtc: '2026-10-16T12:00:00.000000Z', timestampOriginal: '2026-10-16T12:00:00Z', filters: folded('<script>', 'STRASSE') }));
  assert.ok(rendered.includes('class="literal-match"')); assert.ok(rendered.includes('&lt;script&gt;'));
  assert.ok(!rendered.includes('<script>')); assert.ok(!rendered.includes('2026-10-16T12:00:00Z'));
  assert.ok(rendered.includes('data-start="21"')); assert.ok(rendered.includes('Straße</mark>'));
});

test('diagnostic React rows retain their full original prefix and text after clear', () => {
  const rendered = renderToStaticMarkup(createElement(LogText, { rawLine: 'invalid <tag> source', timestampUtc: null, timestampOriginal: 'invalid', filters: [] }));
  assert.equal(rendered, '<span>invalid &lt;tag&gt; source</span>');
});
