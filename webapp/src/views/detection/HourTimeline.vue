<script setup>
import { computed } from 'vue';

const props = defineProps({
  hourEvaluations: { type: Array, default: () => [] },
  windowStart: String,
  windowEnd: String,
});

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString('de-DE', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

const rows = computed(() => {
  const start = props.windowStart ? new Date(props.windowStart) : null;
  const end = props.windowEnd ? new Date(props.windowEnd) : null;
  return props.hourEvaluations
    .filter(e => e.rejection_reasons[0] !== 'out_of_horizon' || e.accepted)
    .map(e => {
      const t = new Date(e.time);
      const inWindow = start && end ? (t >= start && t < end) : false;
      return { ...e, inWindow, label: fmtTime(e.time) };
    });
});
</script>

<template>
  <div class="hour-timeline">
    <div
      v-for="(row, i) in rows"
      :key="i"
      class="hour-row"
      :class="{ 'in-window': row.inWindow, accepted: row.accepted, rejected: !row.accepted }"
    >
      <span class="num" style="color:#52606d">{{ row.label }}</span>
      <span
        class="outcome-pill"
        :class="row.accepted ? 'outcome-pass' : 'outcome-fail'"
      >{{ row.accepted ? 'accepted' : 'rejected' }}</span>
      <span>
        <span
          v-for="reason in row.rejection_reasons"
          :key="reason"
          class="rejection-chip"
        >{{ reason }}</span>
        <span v-if="row.accepted && row.matching_models.length" style="font-size:11px; color:#7b8794">
          {{ row.matching_models.join(', ') }}
        </span>
      </span>
    </div>
    <div v-if="!rows.length" class="empty-state">No hour evaluation data.</div>
  </div>
</template>
