import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { test } from 'node:test';
import ts from 'typescript';
import core from '../src/i18n/core.pl.ts';
import investigation from '../src/i18n/investigation.pl.ts';
import topology from '../src/i18n/topology.pl.ts';
import errors from '../src/i18n/errors.pl.ts';
import { createTranslator, resolveLanguage } from '../src/i18n/translate.ts';

const dictionary = { ...core, ...investigation, ...topology, ...errors };
const placeholders = value => [...value.matchAll(/\{([a-zA-Z][a-zA-Z0-9_]*)\}/g)].map(match => match[1]).sort();

test('account overrides the application language; default follows it', () => {
  assert.equal(resolveLanguage(), 'en');
  assert.equal(resolveLanguage('pl', 'default'), 'pl');
  assert.equal(resolveLanguage('pl', 'en'), 'en');
  assert.equal(resolveLanguage('en', 'pl'), 'pl');
});

test('Polish text preserves interpolation, whitespace and literal user content', () => {
  const t = createTranslator('pl', { 'Hello {name}': 'Witaj {name}' });
  assert.equal(t(' Hello {name} ', { name: '<script>$& {name} Zażółć</script>' }), ' Witaj <script>$& {name} Zażółć</script> ');
  assert.equal(t('Unknown diagnostic: {code}', { code: 123 }), 'Unknown diagnostic: 123');
  assert.equal(t('Hello {name}'), 'Witaj {name}');
  assert.equal(t('constructor'), 'constructor');
  assert.equal(t('  '), '  ');
  assert.equal(createTranslator('en', dictionary)('Language'), 'Language');
  assert.equal(createTranslator('pl', dictionary)('Language'), 'Język');
});

test('every translated message preserves all of its placeholders', () => {
  for (const [key, translated] of Object.entries(dictionary)) {
    assert.ok(translated.trim(), `Empty translation: ${key}`);
    assert.deepEqual(placeholders(translated), placeholders(key), key);
  }
});

test('all literal UI translation keys have bundled Polish text', () => {
  const missing = new Set();
  function scan(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = resolve(directory, entry.name);
      if (entry.isDirectory() && !['api', 'i18n'].includes(entry.name)) scan(path);
      if (!entry.isFile() || !/\.tsx$/.test(path)) continue;
      const tree = ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
      function visit(node) {
        if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 't' && node.arguments[0] && ts.isStringLiteral(node.arguments[0])) {
          const key = node.arguments[0].text.trim();
          if (!Object.hasOwn(dictionary, key)) missing.add(key);
        }
        ts.forEachChild(node, visit);
      }
      visit(tree);
    }
  }
  scan(resolve('src'));
  assert.deepEqual([...missing].sort(), [], 'Untranslated UI keys');
});
