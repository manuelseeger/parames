<script setup>
import { ref, onMounted, watch } from 'vue';
import { api } from '../api.js';
import { navigate } from '../router.js';
import DetectionCard from '../components/detection/DetectionCard.vue';

const detections = ref(null);
const error = ref(null);
// null = live detections only, true = backtests only, 'all' = all
const source = ref(null);

async function loadDetections() {
  error.value = null;
  detections.value = null;
  try {
    detections.value = await api.listDetections(100, source.value === 'all' ? null : source.value);
  } catch (e) {
    error.value = e.message;
  }
}

onMounted(loadDetections);
watch(source, loadDetections);
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 style="margin:0">Detections</h1>
      <div class="segmented-control">
        <button :class="{ active: source === null }" @click="source = null">Live</button>
        <button :class="{ active: source === true }" @click="source = true">Backtests</button>
        <button :class="{ active: source === 'all' }" @click="source = 'all'">All</button>
      </div>
      <span v-if="detections" class="muted" style="font-size:13px">{{ detections.length }} total</span>
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-else-if="!detections" class="spinner">Loading…</div>
    <div v-else-if="detections.length === 0" class="empty-state">No detections yet.</div>
    <div v-else class="detection-grid">
      <DetectionCard v-for="d in detections" :key="d.id" :detection="d" @open="navigate(`/detections/${d.id}`)" />
    </div>
  </div>
</template>
