const BASE = '/api';

async function request(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    let detail;
    try { detail = (await res.json()).detail; } catch { detail = await res.text(); }
    throw new Error(detail || `${res.status} ${res.statusText}`);
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
  listDetections: (limit = 25) => request(`/detections?limit=${limit}`),
  listDeliveries: (limit = 25) => request(`/deliveries?limit=${limit}`),
};
