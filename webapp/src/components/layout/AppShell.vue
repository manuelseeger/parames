<script setup>
import { onMounted, ref } from 'vue';
import { api } from '../../api.js';
import { route } from '../../router.js';

defineProps({ user: { type: Object, required: true } });
const emit = defineEmits(['logout']);
const version = ref(null);

onMounted(async () => {
  try {
    version.value = (await api.health()).version;
  } catch {
    // The UI remains usable when the API is temporarily unavailable.
  }
});

function isActive(prefix) {
  if (prefix === '/') return route.value === '/' || route.value === '';
  return route.value.startsWith(prefix);
}
</script>

<template>
  <div class="app">
    <nav class="nav">
      <span class="brand">Parames</span>
      <span v-if="version" class="app-version">v{{ version }}</span>
      <a v-if="user.role === 'admin'" href="#/" :class="{ active: isActive('/') }">Dashboard</a>
      <a href="#/alerts" :class="{ active: isActive('/alerts') }">Alert definitions</a>
      <a href="#/detections" :class="{ active: isActive('/detections') }">Detections</a>
      <a v-if="user.role === 'admin'" href="#/logs" :class="{ active: isActive('/logs') }">Logs</a>
      <span class="spacer"></span>
      <a href="/api/docs" target="_blank" class="muted">API docs</a>
      <span class="muted">{{ user.email }}</span>
      <button type="button" class="btn btn-sm" @click="emit('logout')">Log out</button>
    </nav>
    <slot />
  </div>
</template>
