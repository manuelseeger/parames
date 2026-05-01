<script setup>
import { ref, reactive, onMounted, computed } from 'vue';
import { api } from '../api.js';
import { navigate } from '../router.js';

const props = defineProps({
  id: { type: String, default: null },
});

function emptyDefinition() {
  return {
    name: '',
    description: '',
    enabled: true,
    location: { name: '', latitude: 0, longitude: 0 },
    models: [],
    forecast_hours: 48,
    wind_level_m: 10,
    model_agreement: {
      required: true,
      min_models_matching: 2,
      max_direction_delta_deg: 35,
      max_speed_delta_kmh: 8,
    },
    wind: {
      min_speed_kmh: 10,
      strong_speed_kmh: null,
      direction_min_deg: 0,
      direction_max_deg: 360,
      min_consecutive_hours: 2,
    },
    time_window: { start_hour: 8, end_hour: 20 },
    dry: { enabled: true, max_precipitation_mm_per_hour: 0.2 },
    plugins: [],
    delivery: [],
    suppress_duplicates: null,
  };
}

function emptyBisePlugin() {
  return {
    type: 'bise',
    enabled: true,
    east_minus_west_pressure_hpa_min: 1.5,
    pressure_reference_west: { name: '', latitude: 0, longitude: 0 },
    pressure_reference_east: { name: '', latitude: 0, longitude: 0 },
  };
}

const def = reactive(emptyDefinition());
const error = ref(null);
const loading = ref(false);
const saving = ref(false);
const modelsText = ref('');
const deliveryText = ref('');
const hasTimeWindow = ref(true);
const hasDry = ref(true);
const hasModelAgreement = ref(true);

const isEdit = computed(() => !!props.id);

onMounted(async () => {
  if (!props.id) return;
  loading.value = true;
  try {
    const data = await api.getAlertDefinition(props.id);
    Object.assign(def, data);
    modelsText.value = (data.models || []).join(', ');
    deliveryText.value = (data.delivery || []).join(', ');
    hasTimeWindow.value = !!data.time_window;
    hasDry.value = !!data.dry;
    hasModelAgreement.value = !!data.model_agreement;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
});

function parseList(text) {
  return text.split(',').map(s => s.trim()).filter(s => s.length > 0);
}

function toggleTimeWindow() {
  hasTimeWindow.value = !hasTimeWindow.value;
  def.time_window = hasTimeWindow.value ? { start_hour: 8, end_hour: 20 } : null;
}

function toggleDry() {
  hasDry.value = !hasDry.value;
  def.dry = hasDry.value ? { enabled: true, max_precipitation_mm_per_hour: 0.2 } : null;
}

function toggleModelAgreement() {
  hasModelAgreement.value = !hasModelAgreement.value;
  def.model_agreement = hasModelAgreement.value
    ? { required: true, min_models_matching: 2, max_direction_delta_deg: 35, max_speed_delta_kmh: 8 }
    : null;
}

function addBisePlugin() { def.plugins.push(emptyBisePlugin()); }
function removePlugin(idx) { def.plugins.splice(idx, 1); }

async function submit() {
  saving.value = true;
  error.value = null;
  try {
    def.models = parseList(modelsText.value);
    def.delivery = parseList(deliveryText.value);

    const payload = JSON.parse(JSON.stringify(def));
    delete payload.id;
    delete payload._id;
    delete payload.created_at;
    delete payload.updated_at;
    const s = payload.wind.strong_speed_kmh;
    if (s === '' || s === null || s === undefined || (typeof s === 'number' && isNaN(s))) {
      payload.wind.strong_speed_kmh = null;
    }

    if (isEdit.value) {
      await api.updateAlertDefinition(props.id, payload);
    } else {
      await api.createAlertDefinition(payload);
    }
    navigate('/alerts');
  } catch (e) {
    error.value = e.message;
  } finally {
    saving.value = false;
  }
}

function cancel() { navigate('/alerts'); }
</script>

<template>
  <div>
    <div class="toolbar">
      <h1>{{ isEdit ? 'Edit alert definition' : 'New alert definition' }}</h1>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="loading" class="spinner">Loading…</div>

    <form v-else @submit.prevent="submit">
      <section class="card">
        <h2>Basic</h2>
        <div class="field">
          <label>Name <span class="muted">(unique)</span></label>
          <input type="text" v-model="def.name" required>
        </div>
        <div class="field">
          <label>Description</label>
          <input type="text" v-model="def.description">
        </div>
        <div class="field-checkbox">
          <input type="checkbox" id="enabled" v-model="def.enabled">
          <label for="enabled">Enabled</label>
        </div>
      </section>

      <section class="card">
        <h2>Location</h2>
        <div class="field-row">
          <div class="field">
            <label>Name</label>
            <input type="text" v-model="def.location.name" required>
          </div>
          <div class="field">
            <label>Latitude</label>
            <input type="number" step="any" v-model.number="def.location.latitude" required>
          </div>
          <div class="field">
            <label>Longitude</label>
            <input type="number" step="any" v-model.number="def.location.longitude" required>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>Forecast models</h2>
        <div class="field">
          <label>Models <span class="muted">(comma-separated)</span></label>
          <input type="text" v-model="modelsText" placeholder="meteoswiss_icon_ch2, icon_d2, ecmwf_ifs">
          <div class="field-help">Open-Meteo model identifiers.</div>
        </div>
      </section>

      <section class="card">
        <h2>Wind</h2>
        <div class="field-row">
          <div class="field">
            <label>Min speed (km/h)</label>
            <input type="number" step="any" v-model.number="def.wind.min_speed_kmh" required>
          </div>
          <div class="field">
            <label>Strong speed (km/h) <span class="muted">(optional)</span></label>
            <input type="number" step="any" v-model.number="def.wind.strong_speed_kmh" placeholder="use global default">
          </div>
          <div class="field">
            <label>Min consecutive hours</label>
            <input type="number" v-model.number="def.wind.min_consecutive_hours" required>
          </div>
        </div>
        <div class="field-row">
          <div class="field">
            <label>Direction min (°)</label>
            <input type="number" min="0" max="360" step="1" v-model.number="def.wind.direction_min_deg" required>
          </div>
          <div class="field">
            <label>Direction max (°)</label>
            <input type="number" min="0" max="360" step="1" v-model.number="def.wind.direction_max_deg" required>
          </div>
        </div>
        <div class="field-help">Use 0–360 for any direction. Wrap-around supported (e.g. 330–30 for N).</div>
      </section>

      <section class="card">
        <div class="section-header">
          <h2>Time window</h2>
          <button type="button" class="btn btn-sm" @click="toggleTimeWindow">
            {{ hasTimeWindow ? 'Remove' : 'Add' }}
          </button>
        </div>
        <div v-if="hasTimeWindow" class="field-row">
          <div class="field">
            <label>Start hour (0–23)</label>
            <input type="number" min="0" max="23" v-model.number="def.time_window.start_hour" required>
          </div>
          <div class="field">
            <label>End hour (1–24)</label>
            <input type="number" min="1" max="24" v-model.number="def.time_window.end_hour" required>
          </div>
        </div>
        <div v-else class="muted">No time window — alerts can fire at any hour.</div>
      </section>

      <section class="card">
        <div class="section-header">
          <h2>Dry filter</h2>
          <button type="button" class="btn btn-sm" @click="toggleDry">
            {{ hasDry ? 'Remove' : 'Add' }}
          </button>
        </div>
        <div v-if="hasDry">
          <div class="field-checkbox">
            <input type="checkbox" id="dry-enabled" v-model="def.dry.enabled">
            <label for="dry-enabled">Enabled</label>
          </div>
          <div class="field">
            <label>Max precipitation (mm/h)</label>
            <input type="number" step="any" v-model.number="def.dry.max_precipitation_mm_per_hour">
          </div>
        </div>
        <div v-else class="muted">No dry filter applied.</div>
      </section>

      <section class="card">
        <div class="section-header">
          <h2>Plugins</h2>
          <button type="button" class="btn btn-sm" @click="addBisePlugin">+ Add bise plugin</button>
        </div>
        <div v-if="def.plugins.length === 0" class="muted">No plugins.</div>
        <div v-for="(p, idx) in def.plugins" :key="idx" class="plugin-entry">
          <div class="plugin-entry-header">
            <span>Type: <code>{{ p.type }}</code></span>
            <button type="button" class="btn btn-sm btn-danger" @click="removePlugin(idx)">Remove</button>
          </div>

          <template v-if="p.type === 'bise'">
            <div class="field-checkbox">
              <input type="checkbox" :id="'bise-en-' + idx" v-model="p.enabled">
              <label :for="'bise-en-' + idx">Enabled</label>
            </div>
            <div class="field-row">
              <div class="field">
                <label>Min E−W gradient (hPa)</label>
                <input type="number" step="any" v-model.number="p.east_minus_west_pressure_hpa_min" required>
              </div>
            </div>
            <h3 style="margin-top: 12px;">West reference</h3>
            <div class="field-row">
              <div class="field">
                <label>Name</label>
                <input type="text" v-model="p.pressure_reference_west.name" required>
              </div>
              <div class="field">
                <label>Latitude</label>
                <input type="number" step="any" v-model.number="p.pressure_reference_west.latitude" required>
              </div>
              <div class="field">
                <label>Longitude</label>
                <input type="number" step="any" v-model.number="p.pressure_reference_west.longitude" required>
              </div>
            </div>
            <h3 style="margin-top: 12px;">East reference</h3>
            <div class="field-row">
              <div class="field">
                <label>Name</label>
                <input type="text" v-model="p.pressure_reference_east.name" required>
              </div>
              <div class="field">
                <label>Latitude</label>
                <input type="number" step="any" v-model.number="p.pressure_reference_east.latitude" required>
              </div>
              <div class="field">
                <label>Longitude</label>
                <input type="number" step="any" v-model.number="p.pressure_reference_east.longitude" required>
              </div>
            </div>
          </template>
        </div>
      </section>

      <section class="card">
        <h2>Delivery</h2>
        <div class="field">
          <label>Channel names <span class="muted">(comma-separated; defined in YAML)</span></label>
          <input type="text" v-model="deliveryText" placeholder="console, telegram" required>
        </div>
      </section>

      <section class="card">
        <h2>Advanced</h2>
        <div class="field-row">
          <div class="field">
            <label>Forecast hours</label>
            <input type="number" v-model.number="def.forecast_hours">
          </div>
          <div class="field">
            <label>Wind level (m)</label>
            <input type="number" v-model.number="def.wind_level_m">
          </div>
        </div>

        <div class="section-header" style="margin-top: 12px;">
          <h3 style="margin: 0;">Model agreement</h3>
          <button type="button" class="btn btn-sm" @click="toggleModelAgreement">
            {{ hasModelAgreement ? 'Remove' : 'Add' }}
          </button>
        </div>
        <div v-if="hasModelAgreement" class="field-row">
          <div class="field-checkbox">
            <input type="checkbox" id="ma-required" v-model="def.model_agreement.required">
            <label for="ma-required">Required</label>
          </div>
          <div class="field">
            <label>Min models matching</label>
            <input type="number" v-model.number="def.model_agreement.min_models_matching">
          </div>
          <div class="field">
            <label>Max direction delta (°)</label>
            <input type="number" step="any" v-model.number="def.model_agreement.max_direction_delta_deg">
          </div>
          <div class="field">
            <label>Max speed delta (km/h)</label>
            <input type="number" step="any" v-model.number="def.model_agreement.max_speed_delta_kmh">
          </div>
        </div>
        <div v-else class="muted">No model agreement check.</div>
      </section>

      <div class="form-actions">
        <button type="button" class="btn" @click="cancel" :disabled="saving">Cancel</button>
        <button type="submit" class="btn btn-primary" :disabled="saving">
          {{ saving ? 'Saving…' : (isEdit ? 'Save changes' : 'Create') }}
        </button>
      </div>
    </form>
  </div>
</template>
