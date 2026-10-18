export type Language = 'en' | 'pl';
export type LanguagePreference = Language | 'default';
export type TranslationValues = Record<string, string | number>;
export type Dictionary = Record<string, string>;

export function resolveLanguage(fallback: Language = 'en', preference: LanguagePreference = 'default'): Language {
  return preference === 'default' ? fallback : preference;
}

// Only UI-authored strings enter this function. Log text, names, Markdown and
// imported documents are rendered directly, never passed through translation.
export function createTranslator(language: Language, dictionary: Dictionary) {
  return (source: string, values: TranslationValues = {}): string => {
    const key = source.trim();
    if (!key) return source;
    const translated = language === 'pl' && Object.hasOwn(dictionary, key) ? dictionary[key] : key;
    const leading = source.slice(0, source.length - source.trimStart().length);
    const trailing = source.slice(source.trimEnd().length);
    return leading + translated.replace(/\{([a-zA-Z][a-zA-Z0-9_]*)\}/g, (match, name: string) =>
      Object.hasOwn(values, name) ? String(values[name]) : match) + trailing;
  };
}
