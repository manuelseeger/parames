<script setup>
import { computed } from 'vue';
import { route, match } from './router.js';
import Dashboard from './views/Dashboard.vue';
import AlertDefinitionsList from './views/AlertDefinitionsList.vue';
import AlertDefinitionForm from './views/AlertDefinitionForm.vue';

const view = computed(() => {
  const path = route.value;
  if (path === '/' || path === '') return { component: Dashboard };
  if (path === '/alerts') return { component: AlertDefinitionsList };
  if (path === '/alerts/new') return { component: AlertDefinitionForm, props: { id: null } };
  const m = match('/alerts/:id', path);
  if (m) return { component: AlertDefinitionForm, props: { id: m.id } };
  return null;
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
      <a href="#/" :class="{ active: isActive('/') }">Dashboard</a>
      <a href="#/alerts" :class="{ active: isActive('/alerts') }">Alert definitions</a>
      <span class="spacer"></span>
      <a href="/api/docs" target="_blank" class="muted">API docs</a>
    </nav>
    <component v-if="view" :is="view.component" v-bind="view.props || {}" />
    <div v-else class="card">Not found: <code>{{ route }}</code></div>
  </div>
</template>
