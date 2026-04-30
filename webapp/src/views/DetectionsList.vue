<script setup>
import { ref, onMounted } from 'vue';
import { api } from '../api.js';
import { navigate } from '../router.js';

const detections = ref(null);
const error = ref(null);

onMounted(async () => {
  try {
    detections.value = await api.listDetections(100);
  } catch (e) {
    error.value = e.message;
  }
});

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function fmtTimeRange(start, end) {
  const s = new Date(start).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  const e = new Date(end).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  return `${s}–${e}`;
}

function classificationPill(c) {
  if (c === 'excellent') return 'pill-excellent';
  if (c === 'strong') return 'pill-ok';
  if (c === 'candidate') return 'pill-warn';
  return 'pill-muted';
}

function dirLabel(deg) {
  return ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(deg / 45) % 8];
}

function sparkPoints(hours) {
  if (!hours || hours.length < 2) return '';
  const W = 120, H = 32;
  const max = Math.max(...hours.map(h => h.avg_wind_speed_kmh)) || 1;
  return hours.map((h, i) => {
    const x = (i / (hours.length - 1)) * W;
    const y = H - (h.avg_wind_speed_kmh / max) * (H - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

function sparkArea(hours) {
  if (!hours || hours.length < 2) return '';
  const W = 120, H = 32;
  const max = Math.max(...hours.map(h => h.avg_wind_speed_kmh)) || 1;
  const pts = hours.map((h, i) => ({
    x: (i / (hours.length - 1)) * W,
    y: H - (h.avg_wind_speed_kmh / max) * (H - 4) - 2,
  }));
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  return `${line} L${pts[pts.length - 1].x.toFixed(1)},${H} L0,${H} Z`;
}

function sparkBand(hours) {
  if (!hours || hours.length < 2) return null;
  const W = 120;
  const inIdx = hours.reduce((acc, h, i) => (h.in_window ? [...acc, i] : acc), []);
  if (!inIdx.length) return null;
  const x1 = (inIdx[0] / (hours.length - 1)) * W;
  const x2 = (inIdx[inIdx.length - 1] / (hours.length - 1)) * W;
  return { x: x1.toFixed(1), width: Math.max(x2 - x1, 2).toFixed(1) };
}
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 style="margin:0">Detections</h1>
      <span v-if="detections" class="muted" style="font-size:13px">{{ detections.length }} total</span>
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-else-if="!detections" class="spinner">Loading…</div>
    <div v-else-if="detections.length === 0" class="empty-state">No detections yet.</div>

    <div v-else class="detection-grid">
      <div
        v-for="d in detections"
        :key="d.id"
        class="detection-card"
        role="button"
        tabindex="0"
        @click="navigate(`/detections/${d.id}`)"
        @keydown.enter="navigate(`/detections/${d.id}`)"
      >
        <!-- Header row: icon + name + classification -->
        <div class="detection-card-header">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="det-icon">
            <path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2"/>
          </svg>
          <span class="detection-card-title">{{ d.alert_name }}</span>
          <span class="pill" :class="classificationPill(d.classification)">{{ d.classification }}</span>
        </div>

        <!-- Date + time range + duration -->
        <div class="detection-card-time">
          {{ fmtDate(d.start) }}
          &ensp;<strong>{{ fmtTimeRange(d.start, d.end) }}</strong>
          &ensp;·&ensp;{{ d.window.duration_hours }}h
        </div>

        <!-- Sparkline: wind speed over time, window band highlighted -->
        <svg
          v-if="d.window.hours.length >= 2"
          viewBox="0 0 120 32"
          width="100%"
          height="38"
          preserveAspectRatio="none"
          class="sparkline-svg"
        >
          <rect x="0" y="0" width="120" height="32" fill="#f9fafb" rx="2"/>
          <rect
            v-if="sparkBand(d.window.hours)"
            :x="sparkBand(d.window.hours).x"
            y="0"
            :width="sparkBand(d.window.hours).width"
            height="32"
            fill="#dbeafe"
          />
          <path :d="sparkArea(d.window.hours)" fill="#93c5fd" fill-opacity="0.45"/>
          <polyline
            :points="sparkPoints(d.window.hours)"
            fill="none"
            stroke="#2563eb"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <div v-else style="height:8px"/>

        <!-- Stats row -->
        <div class="detection-card-stats">
          <span>
            <span class="stat-num">{{ Math.round(d.window.avg_wind_speed_kmh) }}</span>
            <span class="stat-unit"> avg</span>
          </span>
          <span>
            <span class="stat-num">{{ Math.round(d.window.max_wind_speed_kmh) }}</span>
            <span class="stat-unit"> max km/h</span>
          </span>
          <span>
            <span class="stat-num">{{ dirLabel(d.window.avg_direction_deg) }}</span>
            <span class="stat-unit"> ({{ Math.round(d.window.avg_direction_deg) }}°)</span>
          </span>
          <span class="spacer"/>
          <span class="score-badge" :class="`score-${d.classification}`">
            {{ d.score ?? '—' }} pts
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
