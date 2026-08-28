export interface VoiceThemeInput {
  primary_color?: string | null;
  background_color?: string | null;
  color_scheme: 'light' | 'dark';
}

export interface VoiceThemeTokens {
  accent: string;
  pageBg: string;
  cardBg: string;
  headerTint: string;
  fg: string;
  mutedFg: string;
  border: string;
}

const LIGHT_TOKENS = {
  pageBg: '#f4f7f6',
  cardBg: '#ffffff',
  fg: '#0f172a',
  mutedFg: '#475569',
  border: 'rgba(0,0,0,0.1)',
} as const;

const DARK_TOKENS = {
  pageBg: '#0f172a',
  cardBg: '#1e293b',
  fg: '#f1f5f9',
  mutedFg: '#94a3b8',
  border: 'rgba(255,255,255,0.1)',
} as const;

export function resolveVoiceTheme(theme: VoiceThemeInput): VoiceThemeTokens {
  const base = theme.color_scheme === 'dark' ? DARK_TOKENS : LIGHT_TOKENS;
  const accent = theme.primary_color || '#0f766e';
  const pageBg = theme.background_color || base.pageBg;
  return {
    accent,
    pageBg,
    cardBg: base.cardBg,
    headerTint: `color-mix(in srgb, ${accent} 10%, ${base.cardBg})`,
    fg: base.fg,
    mutedFg: base.mutedFg,
    border: base.border,
  };
}
