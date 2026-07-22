<script setup>
import { computed } from 'vue';
import StatusPill from '../ui/StatusPill.vue';
import { directionLabel, formatDate, formatTimeRange } from '../../utils/format.js';

const props = defineProps({ detection: { type: Object, required: true } });
const emit = defineEmits(['open']);

const spark = computed(() => {
  const hours = props.detection.window.hours;
  if (!hours || hours.length < 2) return null;
  const width = 120, height = 32;
  const max = Math.max(...hours.map(hour => hour.avg_wind_speed_kmh)) || 1;
  const points = hours.map((hour, index) => ({
    x: (index / (hours.length - 1)) * width,
    y: height - (hour.avg_wind_speed_kmh / max) * (height - 4) - 2,
  }));
  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
  const inWindow = hours.reduce((indices, hour, index) => hour.in_window ? [...indices, index] : indices, []);
  return {
    points: points.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' '),
    area: `${line} L${points.at(-1).x.toFixed(1)},${height} L0,${height} Z`,
    band: inWindow.length ? {
      x: ((inWindow[0] / (hours.length - 1)) * width).toFixed(1),
      width: Math.max(((inWindow.at(-1) - inWindow[0]) / (hours.length - 1)) * width, 2).toFixed(1),
    } : null,
  };
});
</script>

<template>
  <div class="detection-card" role="button" tabindex="0" @click="emit('open', detection)" @keydown.enter="emit('open', detection)">
    <div class="detection-card-header">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="det-icon">
        <path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2"/>
      </svg>
      <span class="detection-card-title">{{ detection.alert_name }}</span>
      <StatusPill :value="detection.classification" type="classification" />
    </div>
    <div class="detection-card-time">
      {{ formatDate(detection.start) }} &ensp;<strong>{{ formatTimeRange(detection.start, detection.end) }}</strong>
      &ensp;·&ensp;{{ detection.window.duration_hours }}h
    </div>
    <svg v-if="spark" viewBox="0 0 120 32" width="100%" height="38" preserveAspectRatio="none" class="sparkline-svg">
      <rect x="0" y="0" width="120" height="32" fill="#f9fafb" rx="2"/>
      <rect v-if="spark.band" :x="spark.band.x" y="0" :width="spark.band.width" height="32" fill="#dbeafe"/>
      <path :d="spark.area" fill="#93c5fd" fill-opacity="0.45"/>
      <polyline :points="spark.points" fill="none" stroke="#2563eb" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <div v-else style="height:8px"/>
    <div class="detection-card-stats">
      <span><span class="stat-num">{{ Math.round(detection.window.avg_wind_speed_kmh) }}</span><span class="stat-unit"> avg</span></span>
      <span><span class="stat-num">{{ Math.round(detection.window.max_wind_speed_kmh) }}</span><span class="stat-unit"> max km/h</span></span>
      <span><span class="stat-num">{{ directionLabel(detection.window.avg_direction_deg) }}</span><span class="stat-unit"> ({{ Math.round(detection.window.avg_direction_deg) }}°)</span></span>
      <span class="spacer"/>
      <span class="score-badge" :class="`score-${detection.classification}`">{{ detection.score ?? '—' }} pts</span>
    </div>
  </div>
</template>
