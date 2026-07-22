<script setup>
defineProps({ label: String, value: [String, Number], unit: String });
</script>

<template>
  <div class="stat-card">
    <div class="stat-card-label">{{ label }}</div>
    <div class="stat-card-value"><slot name="value">{{ value }}</slot></div>
    <div class="stat-card-unit">{{ unit }}</div>
  </div>
</template>
