import { ref, onMounted } from 'vue';
import { api } from '../api.js';

function fmtDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function fmtTimeRange(start, end) {
  if (!start) return '—';
  const s = new Date(start);
  const e = new Date(end);
  const opts = { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' };
  return `${s.toLocaleString([], opts)} – ${e.toLocaleString([], { hour: '2-digit', minute: '2-digit' })}`;
}

function statusPill(status) {
  if (status === 'completed' || status === 'sent') return 'pill-ok';
  if (status === 'running') return 'pill-warn';
  if (status === 'failed') return 'pill-err';
  return 'pill-muted';
}

function classificationPill(c) {
  if (c === 'strong') return 'pill-ok';
  if (c === 'candidate') return 'pill-warn';
  return 'pill-muted';
}

export const Dashboard = {
  setup() {
    const runs = ref(null);
    const detections = ref(null);
    const deliveries = ref(null);
    const error = ref(null);
    const triggering = ref(false);
    const triggerMsg = ref(null);

    onMounted(async () => {
      try {
        const [r, d, dl] = await Promise.all([
          api.listRuns(25),
          api.listDetections(25),
          api.listDeliveries(25),
        ]);
        runs.value = r;
        detections.value = d;
        deliveries.value = dl;
      } catch (e) {
        error.value = e.message;
      }
    });

    async function runNow() {
      triggering.value = true;
      triggerMsg.value = null;
      try {
        await api.triggerRun();
        triggerMsg.value = 'Run started';
        setTimeout(async () => {
          runs.value = await api.listRuns(25);
        }, 2000);
      } catch (e) {
        triggerMsg.value = 'Error: ' + e.message;
      } finally {
        triggering.value = false;
      }
    }

    return { runs, detections, deliveries, error, triggering, triggerMsg, runNow, fmtDateTime, fmtTimeRange, statusPill, classificationPill };
  },
  template: `
    <div>
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
        <h1 style="margin:0;">Dashboard</h1>
        <button class="btn btn-primary btn-sm" @click="runNow" :disabled="triggering">{{ triggering ? 'Starting…' : 'Run now' }}</button>
        <span v-if="triggerMsg" class="muted" style="font-size:13px;">{{ triggerMsg }}</span>
      </div>
      <div v-if="error" class="error">{{ error }}</div>

      <div class="cards-row">
        <!-- Runs -->
        <section class="card">
          <h2>Recent runs</h2>
          <div v-if="runs === null" class="spinner">Loading…</div>
          <div v-else-if="runs.length === 0" class="empty-state">No runs yet</div>
          <table v-else class="table">
            <thead>
              <tr><th>Started</th><th>Status</th><th class="right">Windows</th><th class="right">Sent</th></tr>
            </thead>
            <tbody>
              <tr v-for="run in runs" :key="run.id">
                <td class="nowrap">{{ fmtDateTime(run.started_at) }}</td>
                <td><span class="pill" :class="statusPill(run.status)">{{ run.status }}</span></td>
                <td class="right">{{ run.windows_found }}</td>
                <td class="right">{{ run.deliveries_attempted }}<span class="muted" v-if="run.deliveries_suppressed"> / {{ run.deliveries_suppressed }}</span></td>
              </tr>
            </tbody>
          </table>
        </section>

        <!-- Detections -->
        <section class="card">
          <h2>Recent detections</h2>
          <div v-if="detections === null" class="spinner">Loading…</div>
          <div v-else-if="detections.length === 0" class="empty-state">No detections yet</div>
          <table v-else class="table">
            <thead>
              <tr><th>Alert</th><th>When</th><th>Class</th><th class="right">Score</th></tr>
            </thead>
            <tbody>
              <tr v-for="d in detections" :key="d.id">
                <td>{{ d.alert_name }}</td>
                <td class="nowrap">{{ fmtTimeRange(d.start, d.end) }}</td>
                <td><span class="pill" :class="classificationPill(d.classification)">{{ d.classification }}</span></td>
                <td class="right">{{ d.score }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <!-- Deliveries -->
        <section class="card">
          <h2>Recent deliveries</h2>
          <div v-if="deliveries === null" class="spinner">Loading…</div>
          <div v-else-if="deliveries.length === 0" class="empty-state">No deliveries yet</div>
          <table v-else class="table">
            <thead>
              <tr><th>Sent</th><th>Channel</th><th>Status</th></tr>
            </thead>
            <tbody>
              <tr v-for="dl in deliveries" :key="dl.id">
                <td class="nowrap">{{ fmtDateTime(dl.sent_at) }}</td>
                <td>{{ dl.channel_name }} <span class="muted">({{ dl.channel_type }})</span></td>
                <td><span class="pill" :class="statusPill(dl.status)">{{ dl.status }}</span></td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </div>
  `,
};
