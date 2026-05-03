<script setup>
import { ref } from 'vue';
import ScoringBreakdown from './ScoringBreakdown.vue';
import HourTimeline from './HourTimeline.vue';
import ModelForecastTable from './ModelForecastTable.vue';
import PluginReportCard from './PluginReportCard.vue';
import ConfigTree from './ConfigTree.vue';

const props = defineProps({
  report: { type: Object, default: null },
  windowStart: String,
  windowEnd: String,
});

const forecastOpen = ref(false);
const profileOpen = ref(false);
</script>

<template>
  <div>
    <!-- Empty state for legacy detections -->
    <div v-if="!report" class="analysis-section">
      <p class="empty-state" style="margin:0">
        No analysis report — re-run this alert to generate one.
      </p>
    </div>

    <template v-else>
      <!-- 1. Final score breakdown -->
      <div class="analysis-section">
        <h3>Score Breakdown</h3>
        <ScoringBreakdown :scoring="report.scoring" />
      </div>

      <!-- 2. Hour evaluation timeline -->
      <div class="analysis-section">
        <h3>Hour Evaluation ({{ report.hour_evaluations.length }} hours)</h3>
        <HourTimeline
          :hour-evaluations="report.hour_evaluations"
          :window-start="report.horizon_start"
          :window-end="report.horizon_end"
        />
      </div>

      <!-- 3. Raw forecasts per model -->
      <div class="analysis-section">
        <div class="collapsible-header" @click="forecastOpen = !forecastOpen">
          <span class="collapsible-arrow" :class="{ open: forecastOpen }">▶</span>
          <h3 style="margin:0">Raw Forecasts ({{ report.forecast_models.join(', ') }})</h3>
        </div>
        <template v-if="forecastOpen">
          <div style="margin-top:10px">
            <ModelForecastTable
              :raw-forecasts="report.raw_forecasts"
              :hour-evaluations="report.hour_evaluations"
              :window-start="report.horizon_start"
              :window-end="report.horizon_end"
            />
          </div>
        </template>
      </div>

      <!-- 4. Plugin reports -->
      <template v-if="report.plugin_reports?.length">
        <h3 style="margin-bottom:8px; color:#52606d">Plugin Reports</h3>
        <PluginReportCard
          v-for="pluginReport in report.plugin_reports"
          :key="pluginReport.type"
          :plugin-type="pluginReport.type"
          :report="pluginReport"
        />
      </template>

      <!-- 5. Profile snapshot -->
      <div class="analysis-section">
        <div class="collapsible-header" @click="profileOpen = !profileOpen">
          <span class="collapsible-arrow" :class="{ open: profileOpen }">▶</span>
          <h3 style="margin:0">Profile Snapshot</h3>
        </div>
        <template v-if="profileOpen">
          <div style="margin-top:10px">
            <ConfigTree :data="report.profile_snapshot" />
          </div>
        </template>
      </div>
    </template>
  </div>
</template>
