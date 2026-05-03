<script setup>
defineProps({ rules: { type: Array, default: () => [] } });

function outcomeClass(outcome) {
  return `outcome-pill outcome-${outcome}`;
}

function fmt(v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}
</script>

<template>
  <table class="rules-table" v-if="rules.length">
    <thead>
      <tr>
        <th>Rule</th>
        <th>Observed</th>
        <th>Threshold</th>
        <th>Outcome</th>
        <th>Δ</th>
        <th>Message</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(r, i) in rules" :key="i">
        <td class="num">{{ r.name }}</td>
        <td class="num">{{ fmt(r.observed) }}</td>
        <td class="num">{{ fmt(r.threshold) }}</td>
        <td><span :class="outcomeClass(r.outcome)">{{ r.outcome }}</span></td>
        <td class="num">{{ r.delta != null ? r.delta : '—' }}</td>
        <td style="color:#7b8794">{{ r.message ?? '' }}</td>
      </tr>
    </tbody>
  </table>
  <div v-else class="empty-state">No rules recorded.</div>
</template>
