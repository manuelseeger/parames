<script setup>
import { ref, computed } from 'vue';
import MetricsGrid from './MetricsGrid.vue';
import RulesTable from './RulesTable.vue';
import ConfigTree from './ConfigTree.vue';

const props = defineProps({
  pluginType: String,
  report: { type: Object, required: true },
});

const open = ref(true);
const hourlyOpen = ref(false);

const hourlyColumns = computed(() => {
  if (!props.report.hourly?.length) return [];
  const keys = new Set();
  for (const h of props.report.hourly) {
    for (const k of Object.keys(h)) keys.add(k);
  }
  return [...keys];
});
</script>

<template>
  <div class="analysis-section">
    <div class="collapsible-header" @click="open = !open">
      <span class="collapsible-arrow" :class="{ open }">▶</span>
      <h3 style="margin:0">{{ pluginType }}</h3>
      <span v-if="report.summary" class="muted" style="font-size:12px; margin-left:8px">{{ report.summary }}</span>
    </div>

    <template v-if="open">
      <!-- Config snapshot -->
      <div v-if="Object.keys(report.config_snapshot || {}).length" style="margin-top:12px">
        <div class="plugin-subheader">Config</div>
        <ConfigTree :data="report.config_snapshot" />
      </div>

      <!-- Inputs -->
      <div v-if="Object.keys(report.inputs || {}).length" style="margin-top:12px">
        <div class="plugin-subheader">Inputs</div>
        <MetricsGrid :data="report.inputs" />
      </div>

      <!-- Aggregate metrics -->
      <div v-if="Object.keys(report.metrics || {}).length" style="margin-top:12px">
        <div class="plugin-subheader">Metrics</div>
        <MetricsGrid :data="report.metrics" />
      </div>

      <!-- Rules -->
      <div v-if="report.rules?.length" style="margin-top:12px">
        <div class="plugin-subheader">Rules</div>
        <RulesTable :rules="report.rules" />
      </div>

      <!-- Hourly trace -->
      <div v-if="report.hourly?.length" style="margin-top:12px">
        <div class="collapsible-header" style="margin-bottom:6px" @click="hourlyOpen = !hourlyOpen">
          <span class="collapsible-arrow" :class="{ open: hourlyOpen }">▶</span>
          <span class="plugin-subheader" style="margin:0">Hourly trace ({{ report.hourly.length }} hours)</span>
        </div>
        <template v-if="hourlyOpen">
          <div style="overflow-x:auto">
            <table class="forecast-table">
              <thead>
                <tr>
                  <th v-for="col in hourlyColumns" :key="col">{{ col }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in report.hourly" :key="i">
                  <td v-for="col in hourlyColumns" :key="col">
                    {{ row[col] != null ? (typeof row[col] === 'object' ? JSON.stringify(row[col]) : row[col]) : '' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>

      <!-- Notes -->
      <div v-if="report.notes?.length" style="margin-top:12px">
        <div class="plugin-subheader">Notes</div>
        <ul style="margin:0; padding-left:16px; font-size:12px; color:#52606d">
          <li v-for="(note, i) in report.notes" :key="i">{{ note }}</li>
        </ul>
      </div>
    </template>
  </div>
</template>
