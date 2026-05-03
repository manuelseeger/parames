<script setup>
import { computed } from 'vue';

const props = defineProps({ scoring: { type: Object, required: true } });

const BAR_COLORS = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f97316'];

const segments = computed(() => {
  const s = props.scoring;
  const total = s.weight_total || 1;
  return Object.entries(s.contributions)
    .filter(([, c]) => c.included)
    .map(([name, c], i) => ({
      name,
      pct: ((c.weight * (c.sub_score ?? 0)) / (total * 100)) * 100,
      color: BAR_COLORS[i % BAR_COLORS.length],
    }));
});

const rows = computed(() => {
  const s = props.scoring;
  return Object.entries(s.contributions).map(([name, c]) => ({
    name,
    weight: c.weight,
    sub_score: c.sub_score,
    weighted_value: c.weighted_value,
    included: c.included,
  }));
});

const tiers = computed(() => {
  const t = props.scoring.tiers;
  return [
    { label: 'Candidate', value: t.candidate_min, pct: t.candidate_min },
    { label: 'Strong', value: t.strong_min, pct: t.strong_min },
    { label: 'Excellent', value: t.excellent_min, pct: t.excellent_min },
  ];
});

function classificationPill(c) {
  if (c === 'excellent') return 'pill-excellent';
  if (c === 'strong') return 'pill-ok';
  if (c === 'candidate') return 'pill-warn';
  return 'pill-muted';
}

function n(v, dp = 2) {
  if (v === null || v === undefined) return '—';
  return typeof v === 'number' ? v.toFixed(dp) : v;
}
</script>

<template>
  <div>
    <!-- Stacked bar -->
    <div class="score-bar-wrap" title="Weighted contributions">
      <div
        v-for="seg in segments"
        :key="seg.name"
        class="score-bar-seg"
        :style="{ width: seg.pct + '%', background: seg.color }"
        :title="`${seg.name}: ${seg.pct.toFixed(1)}%`"
      />
    </div>

    <!-- Breakdown table -->
    <table class="scoring-table">
      <thead>
        <tr>
          <th>Signal</th>
          <th>Weight</th>
          <th>Sub-score</th>
          <th>Weighted</th>
          <th>Included</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.name" :style="r.included ? '' : 'opacity:0.5'">
          <td>{{ r.name }}</td>
          <td class="num">{{ n(r.weight) }}</td>
          <td class="num">{{ r.sub_score != null ? n(r.sub_score, 1) : '—' }}</td>
          <td class="num">{{ r.weighted_value != null ? n(r.weighted_value, 1) : '—' }}</td>
          <td>{{ r.included ? '✓' : '–' }}</td>
        </tr>
      </tbody>
      <tfoot>
        <tr class="sum-row">
          <td>Total</td>
          <td class="num">{{ n(scoring.weight_total) }}</td>
          <td>—</td>
          <td class="num">{{ n(scoring.weighted_sum) }}</td>
          <td>
            <span class="num">raw {{ n(scoring.raw_score, 1) }}</span>
            &nbsp;→&nbsp;
            <strong class="num">{{ scoring.final_score ?? '—' }}</strong>
            &nbsp;
            <span class="pill" :class="classificationPill(scoring.classification)">{{ scoring.classification }}</span>
          </td>
        </tr>
      </tfoot>
    </table>

    <!-- Tier scale -->
    <div style="margin-top:10px; font-size:11px; color:#7b8794">
      Score scale (0–100):
      <div class="tier-scale" style="margin-top:4px">
        <div
          v-for="t in tiers"
          :key="t.label"
          class="tier-marker"
          :style="{ left: t.pct + '%' }"
          :title="`${t.label}: ${t.value}`"
        />
      </div>
      <div style="display:flex; gap:12px; margin-top:4px">
        <span v-for="t in tiers" :key="t.label">{{ t.label }}: {{ t.value }}</span>
      </div>
    </div>
  </div>
</template>
