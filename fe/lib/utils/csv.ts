const needsEscape = /[",\r\n]/;

const escapeCsvField = (value: unknown): string => {
  const raw = value == null ? '' : String(value);
  if (!needsEscape.test(raw)) return raw;
  return `"${raw.replace(/"/g, '""')}"`;
};

export const toCsvText = (headers: string[], rows: Array<Array<unknown>>): string => {
  const headerLine = headers.map(escapeCsvField).join(',');
  const lines = rows.map((row) => row.map(escapeCsvField).join(','));
  return [headerLine, ...lines].join('\r\n');
};

export const downloadUtf8Csv = (filename: string, csvText: string): void => {
  const bom = '\uFEFF';
  const blob = new Blob([bom + csvText], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};
