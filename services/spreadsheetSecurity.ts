export function sanitizeSpreadsheetText(value: unknown): string {
  const text = String(value ?? "");
  return /^\s*[=+\-@]/.test(text) ? `'${text}` : text;
}
