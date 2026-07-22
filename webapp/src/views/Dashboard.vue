<script setup>
import { ref, onMounted } from 'vue';
import { api } from '../api.js';
import { navigate } from '../router.js';
import StatusPill from '../components/ui/StatusPill.vue';
import { formatTimeRange } from '../utils/format.js';

function fmtDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function fmtTimeRange(start, end) {
  return start ? formatTimeRange(start, end, { includeDate: true }) : '—';
}

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
</script>

<template>
  <div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
      <h1 style="margin:0;">Dashboard</h1>
      <button class="btn btn-primary btn-sm" @click="runNow" :disabled="triggering">{{ triggering ? 'Starting…' : 'Run now' }}</button>
      <span v-if="triggerMsg" class="muted" style="font-size:13px;">{{ triggerMsg }}</span>
    </div>
    <div v-if="error" class="error">{{ error }}</div>

    <div class="dash-grid">
      <section class="card dash-runs">
        <h2>Recent runs</h2>
        <div v-if="runs === null" class="spinner">Loading…</div>
        <div v-else-if="runs.length === 0" class="empty-state">No runs yet</div>
        <div v-else class="table-scroll">
          <table class="table">
            <thead>
              <tr>
                <th>Started</th>
                <th>Status</th>
                <th class="right">Windows</th>
                <th class="right">Sent / Suppressed</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in runs" :key="run.id" style="cursor:pointer" @click="navigate(`/logs?run_id=${run.id}`)">
                <td class="nowrap">{{ fmtDateTime(run.started_at) }}</td>
                <td><StatusPill :value="run.status" /></td>
                <td class="right">{{ run.windows_found }}</td>
                <td class="right">
                  {{ run.deliveries_attempted }}
                  <span class="muted" v-if="run.deliveries_suppressed"> / {{ run.deliveries_suppressed }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card">
        <h2>Recent detections</h2>
        <div v-if="detections === null" class="spinner">Loading…</div>
        <div v-else-if="detections.length === 0" class="empty-state">No detections yet</div>
        <div v-else class="table-scroll">
          <table class="table">
            <thead>
              <tr><th>Alert</th><th>Window</th><th>Class</th><th class="right">Score</th></tr>
            </thead>
            <tbody>
              <tr
                v-for="d in detections"
                :key="d.id"
                style="cursor:pointer"
                @click="navigate(`/detections/${d.id}`)"
              >
                <td>{{ d.alert_name }}</td>
                <td class="nowrap">{{ fmtTimeRange(d.start, d.end) }}</td>
                <td><StatusPill :value="d.classification" type="classification" /></td>
                <td class="right">{{ d.score ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card">
        <h2>Recent deliveries</h2>
        <div v-if="deliveries === null" class="spinner">Loading…</div>
        <div v-else-if="deliveries.length === 0" class="empty-state">No deliveries yet</div>
        <div v-else class="table-scroll">
          <table class="table">
            <thead>
              <tr><th>Sent</th><th>Channel</th><th>Status</th></tr>
            </thead>
            <tbody>
              <tr v-for="dl in deliveries" :key="dl.id">
                <td class="nowrap">{{ fmtDateTime(dl.sent_at) }}</td>
                <td>{{ dl.channel_name }} <span class="muted">({{ dl.channel_type }})</span></td>
                <td><StatusPill :value="dl.status" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>
