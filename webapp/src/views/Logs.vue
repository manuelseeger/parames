<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { api } from '../api.js';

const entries = ref([]), nextCursor = ref(null), error = ref(null), newAvailable = ref(false), autoRefresh = ref(false), reverseOrder = ref(false);
const service = ref(''), minLevel = ref(''), search = ref('');
const initialRun = new URLSearchParams((window.location.hash.split('?')[1] || '')).get('run_id') || '';
const runId = ref(initialRun);
let timer;
const filters = computed(() => {
  const p = {};
  if (service.value) p.service = service.value;
  if (minLevel.value) p.min_level = minLevel.value;
  if (search.value) p.search = search.value;
  if (runId.value) p.run_id = runId.value;
  return p;
});
const displayedEntries = computed(() => reverseOrder.value ? [...entries.value].reverse() : entries.value);
function plain(text) { return text.replace(/\x1B(?:[@-_][0-?]*[ -/]*[@-~]|\[[0-?]*[ -/]*[@-~])/g, ''); }
function date(v) { return new Date(v).toLocaleString(); }
async function refresh() {
  try { const page = await api.listLogs(filters.value); entries.value = page.entries; nextCursor.value = page.next_cursor; newAvailable.value = false; } catch (e) { error.value = e.message; }
}
async function loadMore() {
  const page = await api.listLogs({ ...filters.value, cursor: nextCursor.value });
  entries.value.push(...page.entries); nextCursor.value = page.next_cursor;
}
async function poll() {
  try {
    const page = await api.listLogs(filters.value);
    if (page.entries[0] && page.entries[0].id !== entries.value[0]?.id) {
      if (autoRefresh.value) { entries.value = page.entries; nextCursor.value = page.next_cursor; } else newAvailable.value = true;
    }
  } catch (_) {}
}
onMounted(() => { refresh(); timer = setInterval(poll, 5000); });
onBeforeUnmount(() => clearInterval(timer));
</script>

<template>
  <div>
    <h1>Logs</h1>
    <div class="card" style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
      <label>Service <select v-model="service"><option value="">All</option><option>api</option><option>scheduler</option></select></label>
      <label>Minimum severity <select v-model="minLevel"><option value="">All</option><option>INFO</option><option>WARNING</option><option>ERROR</option><option>CRITICAL</option></select></label>
      <label>Search <input v-model="search" @keyup.enter="refresh"></label>
      <label>Run ID <input v-model="runId"></label>
      <button class="btn btn-primary btn-sm" @click="refresh">Refresh</button>
      <label><input type="checkbox" v-model="autoRefresh"> Auto-refresh</label>
      <label><input type="checkbox" v-model="reverseOrder"> Oldest first</label>
    </div>
    <div v-if="newAvailable" class="card" style="margin-top:12px"><button class="btn btn-sm" @click="refresh">New entries available — refresh</button></div>
    <div v-if="error" class="error">{{ error }}</div>
    <div class="card" style="margin-top:12px">
      <div v-if="!entries.length" class="empty-state">No matching logs</div>
      <div v-for="entry in displayedEntries" :key="entry.id" class="log-entry">
        <span class="muted">{{ date(entry.occurred_at) }} {{ entry.service }} {{ entry.level }}{{ entry.logger_name ? ' ' + entry.logger_name : '' }}</span>
        <span class="log-message">{{ plain(entry.text) }}</span>
      </div>
      <button v-if="nextCursor" class="btn btn-sm" @click="loadMore">Load more</button>
    </div>
  </div>
</template>
