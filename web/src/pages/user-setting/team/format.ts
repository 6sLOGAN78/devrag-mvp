/** A server timestamp as a machine value and a localized medium date, or null when it is empty or not a date. */
export function formatDate(value: string, language: string): { iso: string; text: string } | null {
  if (value === "") return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return { iso: date.toISOString(), text: new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(date) };
}
