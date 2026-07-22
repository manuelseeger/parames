const locale = 'de-DE';

export function formatDate(iso, options = { day: '2-digit', month: '2-digit', year: 'numeric' }) {
  return new Date(iso).toLocaleDateString(locale, options);
}

export function formatTime(iso) {
  return new Date(iso).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
}

export function formatTimeRange(start, end, { includeDate = false } = {}) {
  const date = includeDate ? `${formatDate(start, { day: '2-digit', month: '2-digit' })} ` : '';
  return `${date}${formatTime(start)}–${formatTime(end)}`;
}

export function directionLabel(degrees) {
  return ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(degrees / 45) % 8];
}
