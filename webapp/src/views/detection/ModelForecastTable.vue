<script setup>
import { computed } from 'vue';

const props = defineProps({
  rawForecasts: { type: Array, default: () => [] },
  hourEvaluations: { type: Array, default: () => [] },
  windowStart: String,
  windowEnd: String,
});

const FIELDS = ['wind_speed', 'wind_direction', 'wind_gusts', 'precipitation', 'pressure_msl', 'cape', 'showers'];

const models = computed(() => props.rawForecasts.map(s => s.model));

// Union of all timestamps across models
const timestamps = computed(() => {
  const seen = new Set();
  for (const series of props.rawForecasts) {
    for (const h of series.hours) seen.add(h.time);
  }
  return [...seen].sort();
});

// Acceptance state per timestamp
const stateByTime = computed(() => {
  const map = {};
  for (const e of props.hourEvaluations) {
    map[e.time] = e.accepted ? 'accepted' : (e.rejection_reasons[0] === 'out_of_horizon' ? 'horizon' : 'rejected');
  }
  return map;
});

// Lookup: model -> time -> HourForecast
const byModelTime = computed(() => {
  const out = {};
  for (const series of props.rawForecasts) {
    out[series.model] = {};
    for (const h of series.hours) out[series.model][h.time] = h;
  }
  return out;
});

// Only show columns where at least one model has data
const visibleFields = computed(() => {
  return FIELDS.filter(f =>
    props.rawForecasts.some(series => series.hours.some(h => h[f] != null))
  );
});

function isInWindow(ts) {
  if (!props.windowStart || !props.windowEnd) return false;
  const t = new Date(ts);
  return t >= new Date(props.windowStart) && t < new Date(props.windowEnd);
}

function rowClass(ts) {
  const state = stateByTime.value[ts];
  if (isInWindow(ts)) return 'in-window';
  if (state === 'accepted') return 'accepted';
  if (state === 'horizon') return '';
  return 'rejected';
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString('de-DE', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function fmtVal(v) {
  if (v === null || v === undefined) return '';
  return typeof v === 'number' ? v.toFixed(1) : v;
}
</script>

<template>
  <div class="forecast-table-wrap">
    <table class="forecast-table" v-if="timestamps.length">
      <thead>
        <tr>
          <th class="time-col">Time</th>
          <template v-for="m in models" :key="m">
            <th v-for="f in visibleFields" :key="`${m}-${f}`">{{ m.split('_').slice(-1)[0] }} / {{ f.replace('wind_', '') }}</th>
          </template>
        </tr>
      </thead>
      <tbody>
        <tr v-for="ts in timestamps" :key="ts" :class="rowClass(ts)">
          <td class="time-col num">{{ fmtTime(ts) }}</td>
          <template v-for="m in models" :key="m">
            <td v-for="f in visibleFields" :key="`${m}-${f}`">
              {{ fmtVal(byModelTime[m]?.[ts]?.[f]) }}
            </td>
          </template>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state">No raw forecast data.</div>
  </div>
</template>
