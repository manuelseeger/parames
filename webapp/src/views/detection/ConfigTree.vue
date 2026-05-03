<script setup>
import { ref } from 'vue';
defineProps({ data: { type: Object, default: () => ({}) } });

function fmt(v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'object') return JSON.stringify(v, null, 2);
  return String(v);
}
</script>

<template>
  <div class="config-tree">
    <template v-for="(val, key) in data" :key="key">
      <div style="margin-bottom:2px">
        <span class="config-tree-key">{{ key }}:</span>
        <span class="config-tree-val" style="margin-left:8px">{{ fmt(val) }}</span>
      </div>
    </template>
  </div>
</template>
