<script setup>
defineProps({ data: { type: Object, default: () => ({}) } });

function fmt(v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}
</script>

<template>
  <div class="metrics-grid">
    <template v-for="(val, key) in data" :key="key">
      <span class="metrics-key">{{ key }}</span>
      <span class="metrics-val">{{ fmt(val) }}</span>
    </template>
  </div>
</template>
