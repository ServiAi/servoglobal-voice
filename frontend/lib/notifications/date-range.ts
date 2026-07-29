function parseLocalDate(value: string): [number, number, number] {
  const [year, month, day] = value.split('-').map(Number);
  return [year, month, day];
}

export function toLocalDayStartIso(value: string): string {
  const [year, month, day] = parseLocalDate(value);
  return new Date(year, month - 1, day, 0, 0, 0, 0).toISOString();
}

export function toLocalDayEndIso(value: string): string {
  const [year, month, day] = parseLocalDate(value);
  return new Date(year, month - 1, day, 23, 59, 59, 999).toISOString();
}
