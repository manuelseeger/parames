<script setup>
import { ref, computed, onMounted } from 'vue';
import { api } from '../api.js';

const props = defineProps({ id: String });

const detection = ref(null);
const error = ref(null);

onMounted(async () => {
  try {
    detection.value = await api.getDetection(props.id);
  } catch (e) {
    error.value = e.message;
  }
});

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
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

// ── Wind speed chart ─────────────────────────────────────────────────────────
// SVG: 560 × 130, plot area x∈[48,548] y∈[10,100]
const WIND_SVG_W = 560, WIND_SVG_H = 130;
const WML = 48, WMR = 12, WMT = 10, WMB = 30;
const WPW = WIND_SVG_W - WML - WMR;   // 500
const WPH = WIND_SVG_H - WMT - WMB;   // 90
const WBOTTOM = WMT + WPH;            // 100

const windChart = computed(() => {
  const hours = detection.value?.window?.hours;
  if (!hours?.length) return null;
  const N = hours.length;

  const speeds = hours.map(h => h.avg_wind_speed_kmh);
  const maxSpeed = Math.max(...speeds);
  const yMax = Math.ceil((maxSpeed + 5) / 10) * 10;

  const xOf = i => (N === 1 ? WML + WPW / 2 : WML + (i / (N - 1)) * WPW);

  const pts = hours.map((h, i) => ({
    x: xOf(i),
    y: WBOTTOM - (h.avg_wind_speed_kmh / yMax) * WPH,
    inWindow: h.in_window,
    speed: Math.round(h.avg_wind_speed_kmh),
    time: fmtTime(h.time),
    dir: Math.round(h.avg_direction_deg),
  }));

  const linePath = N === 1
    ? `M${pts[0].x - 20},${pts[0].y} L${pts[0].x + 20},${pts[0].y}`
    : pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');

  const areaPath = N === 1
    ? `M${pts[0].x - 20},${pts[0].y} L${pts[0].x + 20},${pts[0].y} L${pts[0].x + 20},${WBOTTOM} L${pts[0].x - 20},${WBOTTOM} Z`
    : `${linePath} L${xOf(N - 1).toFixed(1)},${WBOTTOM} L${xOf(0).toFixed(1)},${WBOTTOM} Z`;

  // Blue band covering the in-window portion
  const winIdx = hours.reduce((a, h, i) => (h.in_window ? [...a, i] : a), []);
  let windowBand = null;
  if (winIdx.length && N > 1) {
    const bx1 = xOf(winIdx[0]);
    const bx2 = xOf(winIdx[winIdx.length - 1]);
    windowBand = { x: bx1.toFixed(1), width: Math.max(bx2 - bx1, 2).toFixed(1) };
  }

  // Y axis: 4 evenly-spaced labels
  const yLabels = [0, 1, 2, 3].map(k => ({
    value: Math.round((k / 3) * yMax),
    y: (WBOTTOM - (k / 3) * WPH).toFixed(1),
  }));

  // X axis: up to 8 time labels
  const xLabels = [];
  const step = Math.max(1, Math.floor(N / 7));
  for (let i = 0; i < N; i++) {
    if (i % step === 0 || i === N - 1) xLabels.push({ x: xOf(i).toFixed(1), label: pts[i].time });
  }

  return { pts, linePath, areaPath, windowBand, yLabels, xLabels };
});

// ── Precipitation chart ───────────────────────────────────────────────────────
// SVG: 560 × 96, plot area x∈[48,548] y∈[10,66]
const PREC_SVG_W = 560, PREC_SVG_H = 96;
const PML = 48, PMR = 12, PMT = 10, PMB = 28;
const PPW = PREC_SVG_W - PML - PMR;   // 500
const PPH = PREC_SVG_H - PMT - PMB;   // 58
const PBOTTOM = PMT + PPH;             // 68

const precipChart = computed(() => {
  const hours = detection.value?.window?.hours;
  if (!hours?.length) return null;
  const N = hours.length;

  const vals = hours.map(h => h.avg_precipitation_mm_per_hour ?? 0);
  const maxVal = Math.max(...vals);
  if (maxVal <= 0) return null;

  const yMax = Math.max(Math.ceil(maxVal * 4) / 4, 0.5); // nearest 0.25, min 0.5
  const slotW = PPW / N;
  const barW = slotW * 0.6;

  const bars = hours.map((h, i) => {
    const v = h.avg_precipitation_mm_per_hour ?? 0;
    const bh = (v / yMax) * PPH;
    return {
      x: (PML + i * slotW + slotW * 0.2).toFixed(1),
      y: (PBOTTOM - bh).toFixed(1),
      width: barW.toFixed(1),
      height: Math.max(bh, 0).toFixed(1),
      inWindow: h.in_window,
      val: v.toFixed(2),
    };
  });

  const xOf = i => PML + i * slotW + barW / 2 + slotW * 0.2;

  const yLabels = [
    { value: '0', y: PBOTTOM },
    { value: (yMax / 2).toFixed(1), y: PMT + PPH / 2 },
    { value: yMax.toFixed(1), y: PMT },
  ];

  const xLabels = [];
  const step = Math.max(1, Math.floor(N / 7));
  for (let i = 0; i < N; i++) {
    if (i % step === 0 || i === N - 1) {
      xLabels.push({ x: xOf(i).toFixed(1), label: fmtTime(hours[i].time) });
    }
  }

  // Window band
  const winIdx = hours.reduce((a, h, i) => (h.in_window ? [...a, i] : a), []);
  let windowBand = null;
  if (winIdx.length && N > 1) {
    const bx1 = PML + winIdx[0] * slotW;
    const bx2 = PML + winIdx[winIdx.length - 1] * slotW + slotW;
    windowBand = { x: bx1.toFixed(1), width: (bx2 - bx1).toFixed(1) };
  }

  return { bars, yLabels, xLabels, windowBand };
});

// ── Hourly direction arrows ───────────────────────────────────────────────────
const hourlyArrows = computed(() => {
  const hours = detection.value?.window?.hours;
  if (!hours?.length) return [];
  const step = hours.length > 16 ? 2 : 1;
  return hours
    .filter((_, i) => i % step === 0)
    .map(h => ({
      time: fmtTime(h.time),
      dir: h.avg_direction_deg,
      inWindow: h.in_window,
      speed: Math.round(h.avg_wind_speed_kmh),
    }));
});
</script>

<template>
  <div>
    <!-- Back link -->
    <div style="margin-bottom:16px">
      <a href="#/detections" class="btn btn-ghost btn-sm" style="padding-left:0">
        ← Detections
      </a>
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-else-if="!detection" class="spinner">Loading…</div>

    <template v-else>
      <!-- Header ────────────────────────────────────────────────────── -->
      <div class="detection-detail-header">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2.5" stroke-linecap="round">
          <path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2"/>
        </svg>
        <h1 class="detection-detail-name">{{ detection.alert_name }}</h1>
        <span class="pill" :class="classificationPill(detection.classification)">{{ detection.classification }}</span>
        <span class="muted" style="font-size:13px">Score {{ detection.score ?? 'unavailable' }}</span>
        <span v-if="detection.seen_count > 1" class="muted" style="font-size:13px">· seen {{ detection.seen_count }}×</span>
      </div>
      <div style="margin-bottom:20px; color:#52606d; font-size:13px">
        {{ fmtDate(detection.start) }}
        &ensp;{{ fmtTime(detection.start) }}–{{ fmtTime(detection.end) }}
      </div>

      <!-- Stat cards ─────────────────────────────────────────────────── -->
      <div class="stat-cards-row">
        <div class="stat-card">
          <div class="stat-card-label">Duration</div>
          <div class="stat-card-value">{{ detection.window.duration_hours }}</div>
          <div class="stat-card-unit">hours</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">Avg Wind</div>
          <div class="stat-card-value">{{ Math.round(detection.window.avg_wind_speed_kmh) }}</div>
          <div class="stat-card-unit">km/h</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">Max Wind</div>
          <div class="stat-card-value">{{ Math.round(detection.window.max_wind_speed_kmh) }}</div>
          <div class="stat-card-unit">km/h</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">Direction</div>
          <div class="stat-card-value" style="font-size:20px">{{ dirLabel(detection.window.avg_direction_deg) }}</div>
          <div class="stat-card-unit">{{ Math.round(detection.window.avg_direction_deg) }}°</div>
        </div>
        <div v-if="detection.window.avg_precipitation_mm_per_hour != null" class="stat-card">
          <div class="stat-card-label">Avg Precip</div>
          <div class="stat-card-value" style="font-size:20px">{{ detection.window.avg_precipitation_mm_per_hour.toFixed(1) }}</div>
          <div class="stat-card-unit">mm/h</div>
        </div>
        <div v-if="detection.window.models.length" class="stat-card">
          <div class="stat-card-label">Models</div>
          <div class="stat-card-value" style="font-size:20px">{{ detection.window.models.length }}</div>
          <div class="stat-card-unit">forecast</div>
        </div>
      </div>

      <!-- Wind speed chart ───────────────────────────────────────────── -->
      <div v-if="windChart" class="chart-section">
        <h3>Wind Speed</h3>
        <svg
          :viewBox="`0 0 ${WIND_SVG_W} ${WIND_SVG_H}`"
          class="chart-svg"
          :style="`max-height:${WIND_SVG_H}px`"
        >
          <!-- Horizontal grid lines -->
          <line
            v-for="yl in windChart.yLabels"
            :key="`wg${yl.value}`"
            :x1="WML" :y1="yl.y"
            :x2="WIND_SVG_W - WMR" :y2="yl.y"
            stroke="#e4e7eb" stroke-width="1"
          />
          <!-- In-window highlight band -->
          <rect
            v-if="windChart.windowBand"
            :x="windChart.windowBand.x" :y="WMT"
            :width="windChart.windowBand.width" :height="WPH"
            fill="#eff6ff"
          />
          <!-- Area fill under the line -->
          <path :d="windChart.areaPath" fill="#bfdbfe" fill-opacity="0.5"/>
          <!-- Wind speed line -->
          <path
            :d="windChart.linePath"
            fill="none"
            stroke="#2563eb"
            stroke-width="2"
            stroke-linejoin="round"
            stroke-linecap="round"
          />
          <!-- Data point dots -->
          <circle
            v-for="(pt, i) in windChart.pts"
            :key="`wpt${i}`"
            :cx="pt.x" :cy="pt.y" r="2.5"
            :fill="pt.inWindow ? '#2563eb' : '#93c5fd'"
            stroke="#fff" stroke-width="1.5"
          />
          <!-- Y axis -->
          <line :x1="WML" :y1="WMT" :x2="WML" :y2="WBOTTOM" stroke="#cbd2d9" stroke-width="1"/>
          <text
            v-for="yl in windChart.yLabels"
            :key="`wyl${yl.value}`"
            :x="WML - 5" :y="+yl.y + 4"
            text-anchor="end" font-size="10" fill="#7b8794"
          >{{ yl.value }}</text>
          <!-- Y axis unit -->
          <text
            :x="10" :y="WMT + WPH / 2 + 4"
            text-anchor="middle" font-size="10" fill="#7b8794"
            :transform="`rotate(-90, 10, ${WMT + WPH / 2})`"
          >km/h</text>
          <!-- X axis -->
          <line :x1="WML" :y1="WBOTTOM" :x2="WIND_SVG_W - WMR" :y2="WBOTTOM" stroke="#cbd2d9" stroke-width="1"/>
          <text
            v-for="(xl, i) in windChart.xLabels"
            :key="`wxl${i}`"
            :x="xl.x" :y="WBOTTOM + 14"
            text-anchor="middle" font-size="10" fill="#7b8794"
          >{{ xl.label }}</text>
        </svg>
      </div>

      <!-- Wind direction ──────────────────────────────────────────────── -->
      <div class="chart-section">
        <h3>Wind Direction</h3>
        <div class="direction-row">
          <!-- Compass rose -->
          <div class="compass-wrap">
            <svg viewBox="0 0 96 96" width="96" height="96">
              <!-- Background circle -->
              <circle cx="48" cy="48" r="42" fill="#f9fafb" stroke="#e4e7eb" stroke-width="1.5"/>
              <!-- Intercardinal tick marks -->
              <line x1="48" y1="10" x2="48" y2="17" stroke="#e4e7eb" stroke-width="1.5"/>
              <line x1="86" y1="48" x2="79" y2="48" stroke="#e4e7eb" stroke-width="1.5"/>
              <line x1="48" y1="86" x2="48" y2="79" stroke="#e4e7eb" stroke-width="1.5"/>
              <line x1="10" y1="48" x2="17" y2="48" stroke="#e4e7eb" stroke-width="1.5"/>
              <!-- Cardinal labels -->
              <text x="48" y="9" text-anchor="middle" font-size="10" font-weight="700" fill="#52606d">N</text>
              <text x="88" y="51" text-anchor="start" font-size="10" font-weight="700" fill="#52606d">E</text>
              <text x="48" y="92" text-anchor="middle" font-size="10" font-weight="700" fill="#52606d">S</text>
              <text x="8" y="51" text-anchor="end" font-size="10" font-weight="700" fill="#52606d">W</text>
              <!-- Direction arrow pointing where wind is going TO -->
              <g :transform="`rotate(${(Math.round(detection.window.avg_direction_deg) + 180) % 360}, 48, 48)`">
                <!-- Arrowhead pointing to source -->
                <polygon points="48,18 43,32 53,32" fill="#2563eb"/>
                <!-- Shaft -->
                <line x1="48" y1="32" x2="48" y2="52" stroke="#2563eb" stroke-width="2.5" stroke-linecap="round"/>
                <!-- Tail (dashed, pointing away from source) -->
                <line x1="48" y1="52" x2="48" y2="68" stroke="#93c5fd" stroke-width="2" stroke-dasharray="3,3" stroke-linecap="round"/>
              </g>
              <!-- Center hub -->
              <circle cx="48" cy="48" r="3.5" fill="#1f2933"/>
              <!-- Degree label in center area -->
              <text x="48" y="80" text-anchor="middle" font-size="9" fill="#7b8794">{{ dirLabel(detection.window.avg_direction_deg) }} · {{ Math.round(detection.window.avg_direction_deg) }}°</text>
            </svg>
          </div>

          <!-- Hourly direction arrow strip -->
          <div class="hourly-arrows">
            <div
              v-for="(h, i) in hourlyArrows"
              :key="i"
              class="hour-arrow"
              :class="{ 'hour-arrow-context': !h.inWindow }"
            >
              <svg width="22" height="22" viewBox="0 0 22 22">
                <g :transform="`rotate(${(h.dir + 180) % 360}, 11, 11)`">
                  <polygon points="11,2 8,10 14,10" :fill="h.inWindow ? '#2563eb' : '#93c5fd'"/>
                  <line x1="11" y1="10" x2="11" y2="18" :stroke="h.inWindow ? '#2563eb' : '#93c5fd'" stroke-width="1.5" stroke-linecap="round"/>
                </g>
              </svg>
              <span class="hour-arrow-label">{{ h.time }}</span>
              <span class="hour-arrow-speed">{{ h.speed }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Precipitation chart ─────────────────────────────────────────── -->
      <div v-if="precipChart" class="chart-section">
        <h3>Precipitation</h3>
        <svg
          :viewBox="`0 0 ${PREC_SVG_W} ${PREC_SVG_H}`"
          class="chart-svg"
          :style="`max-height:${PREC_SVG_H}px`"
        >
          <!-- In-window band -->
          <rect
            v-if="precipChart.windowBand"
            :x="precipChart.windowBand.x" :y="PMT"
            :width="precipChart.windowBand.width" :height="PPH"
            fill="#eff6ff"
          />
          <!-- Bars -->
          <rect
            v-for="(bar, i) in precipChart.bars"
            :key="`pb${i}`"
            :x="bar.x" :y="bar.y"
            :width="bar.width" :height="bar.height"
            :fill="bar.inWindow ? '#60a5fa' : '#bfdbfe'"
            rx="1.5"
          />
          <!-- Y axis -->
          <line :x1="PML" :y1="PMT" :x2="PML" :y2="PBOTTOM" stroke="#cbd2d9" stroke-width="1"/>
          <text
            v-for="yl in precipChart.yLabels"
            :key="`pyl${yl.value}`"
            :x="PML - 5" :y="+yl.y + 4"
            text-anchor="end" font-size="10" fill="#7b8794"
          >{{ yl.value }}</text>
          <text
            :x="10" :y="PMT + PPH / 2 + 4"
            text-anchor="middle" font-size="10" fill="#7b8794"
            :transform="`rotate(-90, 10, ${PMT + PPH / 2})`"
          >mm/h</text>
          <!-- X axis -->
          <line :x1="PML" :y1="PBOTTOM" :x2="PREC_SVG_W - PMR" :y2="PBOTTOM" stroke="#cbd2d9" stroke-width="1"/>
          <text
            v-for="(xl, i) in precipChart.xLabels"
            :key="`pxl${i}`"
            :x="xl.x" :y="PBOTTOM + 14"
            text-anchor="middle" font-size="10" fill="#7b8794"
          >{{ xl.label }}</text>
        </svg>
      </div>

      <!-- Models ──────────────────────────────────────────────────────── -->
      <div class="chart-section">
        <h3>Forecast models</h3>
        <div class="models-list">
          <span v-for="m in detection.window.models" :key="m" class="model-tag">{{ m }}</span>
        </div>
        <div v-if="detection.window.dry_filter_applied" style="margin-top:8px; font-size:12px; color:#7b8794">
          Dry filter applied
        </div>
      </div>

      <!-- Plugin outputs ──────────────────────────────────────────────── -->
      <div v-if="Object.keys(detection.window.plugin_outputs).length" class="chart-section">
        <h3>Plugin outputs</h3>
        <div
          v-for="(output, plugin) in detection.window.plugin_outputs"
          :key="plugin"
          class="plugin-block"
        >
          <div class="plugin-block-name">{{ plugin }}</div>
          <div class="plugin-kv">
            <template v-for="(val, key) in output" :key="key">
              <span class="plugin-key">{{ key }}</span>
              <span class="plugin-val">{{ val }}</span>
            </template>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
