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

function emptyLaminarPlugin() {
  return {
    type: 'laminar',
    enabled: true,
    primary_model: null,
    secondary_model: null,
    wind_level_m: 10,
    gust_factor: { good_max: 1.35, marginal_max: 1.60 },
    gust_spread_kmh: { good_max: 6.0, marginal_max: 10.0 },
    direction_variability_deg: { good_max: 20, marginal_max: 40 },
    speed_range_kmh: { good_max: 4.0, marginal_max: 7.0 },
    cape_j_kg: { good_max: 50, marginal_max: 200 },
    model_agreement: {
      direction_good_max_deg: 25,
      direction_marginal_max_deg: 40,
      speed_good_max_kmh: 5.0,
      speed_marginal_max_kmh: 8.0,
    },
    pressure_tendency_3h_hpa: { good_max_abs: 1.5, marginal_max_abs: 2.5 },
    precipitation: { max_precip_mm_h: 0.0, max_showers_mm_h: 0.0 },
  };
}

const PLUGIN_FACTORIES = {
  bise: emptyBisePlugin,
  laminar: emptyLaminarPlugin,
};

const def = reactive(emptyDefinition());
const error = ref(null);
const loading = ref(false);
const saving = ref(false);
const modelsText = ref('');
const deliveryText = ref('');
const hasTimeWindow = ref(true);
const hasDry = ref(true);
const hasModelAgreement = ref(true);
const newPluginType = ref('laminar');

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

function addPlugin() {
  const factory = PLUGIN_FACTORIES[newPluginType.value];
  if (factory) def.plugins.push(factory());
}
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
    // Coerce empty-string optional fields on plugins to null.
    for (const p of (payload.plugins || [])) {
      if (p.type === 'laminar') {
        if (!p.primary_model) p.primary_model = null;
        if (!p.secondary_model) p.secondary_model = null;
      }
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
          <div class="plugin-add-row">
            <select v-model="newPluginType" class="select-sm">
              <option value="laminar">laminar</option>
              <option value="bise">bise</option>
            </select>
            <button type="button" class="btn btn-sm" @click="addPlugin">+ Add plugin</button>
          </div>
        </div>
        <div v-if="def.plugins.length === 0" class="muted">No plugins.</div>
        <div v-for="(p, idx) in def.plugins" :key="idx" class="plugin-entry">
          <div class="plugin-entry-header">
            <span>Type: <code>{{ p.type }}</code></span>
            <button type="button" class="btn btn-sm btn-danger" @click="removePlugin(idx)">Remove</button>
          </div>

          <!-- Bise plugin fields -->
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
            <h3 class="plugin-subheader">West reference</h3>
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
            <h3 class="plugin-subheader">East reference</h3>
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

          <!-- Laminar plugin fields -->
          <template v-else-if="p.type === 'laminar'">
            <div class="field-checkbox">
              <input type="checkbox" :id="'lam-en-' + idx" v-model="p.enabled">
              <label :for="'lam-en-' + idx">Enabled</label>
            </div>
            <div class="field-row">
              <div class="field">
                <label>Primary model <span class="muted">(optional)</span></label>
                <input type="text" v-model="p.primary_model" placeholder="e.g. icon_d2">
              </div>
              <div class="field">
                <label>Secondary model <span class="muted">(optional)</span></label>
                <input type="text" v-model="p.secondary_model" placeholder="e.g. ecmwf_ifs">
              </div>
              <div class="field">
                <label>Wind level (m)</label>
                <input type="number" v-model.number="p.wind_level_m" required>
              </div>
            </div>
            <h3 class="plugin-subheader">Thresholds <span class="muted">(good max / marginal max)</span></h3>
            <div class="threshold-grid">
              <div class="threshold-row">
                <span class="threshold-label">Gust factor</span>
                <input type="number" step="0.01" v-model.number="p.gust_factor.good_max">
                <input type="number" step="0.01" v-model.number="p.gust_factor.marginal_max">
              </div>
              <div class="threshold-row">
                <span class="threshold-label">Gust spread (km/h)</span>
                <input type="number" step="0.5" v-model.number="p.gust_spread_kmh.good_max">
                <input type="number" step="0.5" v-model.number="p.gust_spread_kmh.marginal_max">
              </div>
              <div class="threshold-row">
                <span class="threshold-label">Direction variability (°)</span>
                <input type="number" step="1" v-model.number="p.direction_variability_deg.good_max">
                <input type="number" step="1" v-model.number="p.direction_variability_deg.marginal_max">
              </div>
              <div class="threshold-row">
                <span class="threshold-label">Speed range (km/h)</span>
                <input type="number" step="0.5" v-model.number="p.speed_range_kmh.good_max">
                <input type="number" step="0.5" v-model.number="p.speed_range_kmh.marginal_max">
              </div>
              <div class="threshold-row">
                <span class="threshold-label">CAPE (J/kg)</span>
                <input type="number" step="10" v-model.number="p.cape_j_kg.good_max">
                <input type="number" step="10" v-model.number="p.cape_j_kg.marginal_max">
              </div>
              <div class="threshold-row">
                <span class="threshold-label">Pressure tendency abs (hPa/3h)</span>
                <input type="number" step="0.1" v-model.number="p.pressure_tendency_3h_hpa.good_max_abs">
                <input type="number" step="0.1" v-model.number="p.pressure_tendency_3h_hpa.marginal_max_abs">
              </div>
            </div>
            <h3 class="plugin-subheader">Model agreement</h3>
            <div class="field-row">
              <div class="field">
                <label>Direction good max (°)</label>
                <input type="number" step="1" v-model.number="p.model_agreement.direction_good_max_deg">
              </div>
              <div class="field">
                <label>Direction marginal max (°)</label>
                <input type="number" step="1" v-model.number="p.model_agreement.direction_marginal_max_deg">
              </div>
              <div class="field">
                <label>Speed good max (km/h)</label>
                <input type="number" step="0.5" v-model.number="p.model_agreement.speed_good_max_kmh">
              </div>
              <div class="field">
                <label>Speed marginal max (km/h)</label>
                <input type="number" step="0.5" v-model.number="p.model_agreement.speed_marginal_max_kmh">
              </div>
            </div>
            <h3 class="plugin-subheader">Precipitation</h3>
            <div class="field-row">
              <div class="field">
                <label>Max precip (mm/h)</label>
                <input type="number" step="0.1" v-model.number="p.precipitation.max_precip_mm_h">
              </div>
              <div class="field">
                <label>Max showers (mm/h)</label>
                <input type="number" step="0.1" v-model.number="p.precipitation.max_showers_mm_h">
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
