<script setup>
import { ref, onMounted } from 'vue';
import { api } from '../api.js';
import { navigate } from '../router.js';

const items = ref(null);
const error = ref(null);

async function load() {
  try {
    items.value = await api.listAlertDefinitions();
  } catch (e) {
    error.value = e.message;
  }
}

onMounted(load);

async function toggleEnabled(item) {
  try {
    const next = !item.enabled;
    const updated = await api.patchAlertDefinition(item.id, { enabled: next });
    Object.assign(item, updated);
  } catch (e) {
    error.value = e.message;
  }
}

async function remove(item) {
  if (!confirm(`Delete alert definition "${item.name}"?`)) return;
  try {
    await api.deleteAlertDefinition(item.id);
    items.value = items.value.filter(i => i.id !== item.id);
  } catch (e) {
    error.value = e.message;
  }
}

function edit(item) { navigate(`/alerts/${item.id}`); }
function create() { navigate('/alerts/new'); }
</script>

<template>
  <div>
    <div class="toolbar">
      <h1>Alert definitions</h1>
      <button class="btn btn-primary" @click="create">+ New</button>
    </div>
    <div v-if="error" class="error">{{ error }}</div>

    <div class="card" style="padding: 0;">
      <div v-if="items === null" class="spinner">Loading…</div>
      <div v-else-if="items.length === 0" class="empty-state">No alert definitions. Click "+ New" to create one.</div>
      <table v-else class="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Location</th>
            <th>Models</th>
            <th>Plugins</th>
            <th>Delivery</th>
            <th>Enabled</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>
              <a href="#" @click.prevent="edit(item)"><strong>{{ item.name }}</strong></a>
              <div v-if="item.description" class="muted" style="font-size: 12px;">{{ item.description }}</div>
            </td>
            <td>{{ item.location.name }}</td>
            <td><code>{{ item.models.join(', ') }}</code></td>
            <td>
              <span v-if="item.plugins.length === 0" class="muted">none</span>
              <span v-for="p in item.plugins" :key="p.type" class="pill pill-muted" style="margin-right: 4px;">{{ p.type }}</span>
            </td>
            <td>{{ item.delivery.join(', ') }}</td>
            <td>
              <label class="row">
                <input type="checkbox" :checked="item.enabled" @change="toggleEnabled(item)">
                <span class="muted">{{ item.enabled ? 'on' : 'off' }}</span>
              </label>
            </td>
            <td class="actions">
              <button class="btn btn-sm" @click="edit(item)">Edit</button>
              <button class="btn btn-sm btn-danger" @click="remove(item)">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
