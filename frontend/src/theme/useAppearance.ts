import { useEffect } from 'react';
import type { Bootstrap, Preferences } from '../api/types';

export function useAppearance(bootstrap: Bootstrap | null, preferences: Preferences | null) {
  const mode = preferences?.theme_mode ?? 'default';
  const fallback = bootstrap?.default_theme_mode ?? 'dark';
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const resolved = mode === 'default' ? fallback : mode;
    const apply = () => { document.documentElement.dataset.theme = resolved === 'system' ? (media.matches ? 'dark' : 'light') : resolved; };
    apply();
    if (resolved === 'system') media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [mode, fallback]);
}
