<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { route, match, replaceRoute } from './router.js';
import { api } from './api.js';
import AppShell from './components/layout/AppShell.vue';
import Dashboard from './views/Dashboard.vue';
import AlertDefinitionsList from './views/AlertDefinitionsList.vue';
import AlertDefinitionForm from './views/AlertDefinitionForm.vue';
import DetectionsList from './views/DetectionsList.vue';
import DetectionDetail from './views/DetectionDetail.vue';
import Logs from './views/Logs.vue';
import AuthForm from './views/AuthForm.vue';

const session = ref({ kind: 'loading' });
const sessionKey = ref(0);
const authError = ref('');
const submitting = ref(false);
const isAdmin = computed(() => session.value.kind === 'user' && session.value.user.role === 'admin');

function home(user) {
  return user.role === 'admin' ? '/' : '/alerts';
}

function allowed(path, user) {
  if (path === '/' || path.startsWith('/logs')) return user.role === 'admin';
  return path === '/alerts' || path === '/alerts/new' || !!match('/alerts/:id', path)
    || path === '/detections' || !!match('/detections/:id', path);
}

watch(route, (path) => {
  if (session.value.kind === 'guest') authError.value = '';
  if (session.value.kind === 'user' && !allowed(path, session.value.user)
      && (path === '/' || path.startsWith('/logs') || path === '/login' || path === '/signup')) {
    replaceRoute(home(session.value.user));
  }
});

function enter(user) {
  sessionKey.value += 1;
  session.value = { kind: 'user', user };
  if (!allowed(route.value, user)) replaceRoute(home(user));
}

onMounted(async () => {
  try {
    enter(await api.me());
  } catch (error) {
    session.value = { kind: 'guest' };
    if (error.status !== 401) authError.value = error.message;
    if (route.value !== '/signup') replaceRoute('/login');
  }
});

async function authenticate({ mode, email, password }) {
  if (submitting.value) return;
  authError.value = '';
  submitting.value = true;
  try {
    const user = await api[mode]({ email, password });
    replaceRoute(home(user));
    enter(user);
  } catch (error) {
    authError.value = error.message;
  } finally {
    submitting.value = false;
  }
}

async function logout() {
  const user = session.value.user;
  session.value = { kind: 'loading' };
  authError.value = '';
  try {
    await api.logout();
    sessionKey.value += 1;
    session.value = { kind: 'guest' };
    replaceRoute('/login');
  } catch (error) {
    authError.value = error.message;
    session.value = { kind: 'user', user };
  }
}

const view = computed(() => {
  if (session.value.kind !== 'user') return null;
  const path = route.value;
  if (!allowed(path, session.value.user)) return null;
  if (path === '/') return { component: Dashboard };
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
  <div v-if="session.kind === 'loading'" class="auth-page"><div class="card">Loading…</div></div>
  <div v-else-if="session.kind === 'guest'" class="auth-page">
    <AuthForm :mode="route === '/signup' ? 'signup' : 'login'" :error="authError" :submitting="submitting" @submit="authenticate" />
  </div>
  <AppShell v-else :key="sessionKey" :user="session.user" @logout="logout">
    <div v-if="authError" class="error">{{ authError }}</div>
    <component v-if="view" :is="view.component" :key="route" v-bind="view.props || {}" :is-admin="isAdmin" />
    <div v-else class="card">Not found: <code>{{ route }}</code></div>
  </AppShell>
</template>
