export function formatCrmDate(value?: string | null, options?: Intl.DateTimeFormatOptions) {
  if (!value) return 'Sin registrar';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('es-CO', options ?? { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

export function formatDuration(seconds?: number | null) {
  if (seconds === undefined || seconds === null) return null;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return minutes ? `${minutes} min ${remainder} s` : `${remainder} s`;
}
