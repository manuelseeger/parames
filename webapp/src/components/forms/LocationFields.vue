<script setup>
defineProps({ location: { type: Object, required: true } });
</script>

<template>
  <div class="field-row">
    <div class="field">
      <label>Name</label>
      <input type="text" v-model="location.name" required>
    </div>
    <div class="field">
      <label>Latitude</label>
      <input type="number" step="any" v-model.number="location.latitude" required>
    </div>
    <div class="field">
      <label>Longitude</label>
      <input type="number" step="any" v-model.number="location.longitude" required>
    </div>
  </div>
</template>
