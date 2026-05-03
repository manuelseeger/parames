const BASE = '/api';

async function request(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    let message;
    try {
      const detail = (await res.json()).detail;
      if (Array.isArray(detail)) {
        message = detail
          .map(e => `${e.loc.slice(1).join('.')}: ${e.msg}`)
          .join('\n');
      } else {
        message = detail;
      }
    } catch {
      message = await res.text();
    }
    throw new Error(message || `${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // alert definitions
  listAlertDefinitions: () => request('/alert-definitions'),
  getAlertDefinition: (id) => request(`/alert-definitions/${id}`),
  createAlertDefinition: (body) =>
    request('/alert-definitions', { method: 'POST', body: JSON.stringify(body) }),
  updateAlertDefinition: (id, body) =>
    request(`/alert-definitions/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  patchAlertDefinition: (id, body) =>
    request(`/alert-definitions/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteAlertDefinition: (id) =>
    request(`/alert-definitions/${id}`, { method: 'DELETE' }),

  // dashboard
  triggerRun: () => request('/runs', { method: 'POST' }),
  listRuns: (limit = 25) => request(`/runs?limit=${limit}`),
  listDetections: (limit = 25, isBacktest = null) => {
    const params = new URLSearchParams({ limit });
    if (isBacktest !== null) params.set('is_backtest', isBacktest);
    return request(`/detections?${params}`);
  },
  getDetection: (id) => request(`/detections/${id}`),
  listDeliveries: (limit = 25) => request(`/deliveries?limit=${limit}`),
};
