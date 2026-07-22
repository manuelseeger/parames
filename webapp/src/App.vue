<script setup>
import { computed } from 'vue';
import { route, match } from './router.js';
import AppShell from './components/layout/AppShell.vue';
import Dashboard from './views/Dashboard.vue';
import AlertDefinitionsList from './views/AlertDefinitionsList.vue';
import AlertDefinitionForm from './views/AlertDefinitionForm.vue';
import DetectionsList from './views/DetectionsList.vue';
import DetectionDetail from './views/DetectionDetail.vue';
import Logs from './views/Logs.vue';

const view = computed(() => {
  const path = route.value;
  if (path === '/' || path === '') return { component: Dashboard };
  if (path === '/alerts') return { component: AlertDefinitionsList };
  if (path === '/alerts/new') return { component: AlertDefinitionForm, props: { id: null } };
  const ma = match('/alerts/:id', path);
  if (ma) return { component: AlertDefinitionForm, props: { id: ma.id } };
  if (path.startsWith('/logs')) return { component: Logs };
  if (path === '/detections') return { component: DetectionsList };
  const md = match('/detections/:id', path);
  if (md) return { component: DetectionDetail, props: { id: md.id } };
  return null;
});

</script>

<template>
  <AppShell>
    <component v-if="view" :is="view.component" v-bind="view.props || {}" />
    <div v-else class="card">Not found: <code>{{ route }}</code></div>
  </AppShell>
</template>
