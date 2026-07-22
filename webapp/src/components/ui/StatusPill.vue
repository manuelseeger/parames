<script setup>
import { computed } from 'vue';

const props = defineProps({
  value: { type: String, required: true },
  type: { type: String, default: 'status' },
});

const pillClass = computed(() => {
  if (props.type === 'classification') {
    if (props.value === 'excellent') return 'pill-excellent';
    if (props.value === 'strong') return 'pill-ok';
    if (props.value === 'candidate') return 'pill-warn';
    return 'pill-muted';
  }
  if (['completed', 'sent'].includes(props.value)) return 'pill-ok';
  if (props.value === 'running') return 'pill-warn';
  if (props.value === 'failed') return 'pill-err';
  return 'pill-muted';
});
</script>

<template>
  <span class="pill" :class="pillClass"><slot>{{ value }}</slot></span>
</template>
