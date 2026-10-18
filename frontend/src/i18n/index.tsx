import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import core from './core.pl';
import investigation from './investigation.pl';
import topology from './topology.pl';
import errors from './errors.pl';
import generalTooltips from './general-tooltips.pl';
import logTooltips from './log-tooltips.pl';
import topologyTooltips from './topology-tooltips.pl';
import { createTranslator, type Language } from './translate';

export { resolveLanguage } from './translate';
export type { Language, LanguagePreference } from './translate';

const dictionary = { ...core, ...investigation, ...topology, ...errors, ...generalTooltips, ...logTooltips, ...topologyTooltips };
const I18nContext = createContext({ language: 'en' as Language, t: createTranslator('en', dictionary) });

export function useTranslator(language: Language) {
  return useMemo(() => createTranslator(language, dictionary), [language]);
}

export function I18nProvider({ language, children }: { language: Language; children: ReactNode }) {
  const t = useTranslator(language);
  const value = useMemo(() => ({ language, t }), [language, t]);
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() { return useContext(I18nContext); }
