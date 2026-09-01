<template>
  <div class="spectrum">
    <div class="label">{{ kind === 'ir' ? 'INFRARED SPECTRUM' : 'ABSORPTION SPECTRUM' }}</div>
    <div ref="chartEl" class="chart"></div>

    <!-- 热力学量（仅红外） -->
    <div v-if="kind === 'ir' && thermo" class="thermo">
      <div v-for="(v, k) in thermo" :key="k" class="thermo-item">
        <span class="t-key">{{ k }}</span>
        <span class="t-val">{{ v }}</span>
      </div>
    </div>

    <!-- 激发态列表（仅吸收） -->
    <table v-if="kind === 'absorption'" class="state-table">
      <thead>
        <tr><th>态</th><th>能量 (eV)</th><th>波长 (nm)</th><th>振子强度 f</th></tr>
      </thead>
      <tbody>
        <tr v-for="s in states" :key="s.n">
          <td>S{{ s.n }}</td>
          <td>{{ s.energy_eV.toFixed(2) }}</td>
          <td>{{ s.wavelength_nm }}</td>
          <td>{{ s.osc_strength.toFixed(3) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as echarts from 'echarts'
import type { ExcitedState } from '@/types'

const props = defineProps<{
  kind: 'absorption' | 'ir'
  states?: ExcitedState[]
  freqs?: number[]
  intensities?: number[]
  thermo?: Record<string, string>
}>()

const chartEl = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

function render() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)

  if (props.kind === 'absorption' && props.states) {
    chart.setOption({
      title: { text: 'TD-DFT 吸收光谱', left: 'center', textStyle: { fontSize: 13 } },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'value',
        name: '波长 (nm)',
      },
      yAxis: { type: 'value', name: '振子强度 f' },
      series: [
        {
          type: 'bar',
          barWidth: 4,
          data: props.states.map((s) => [s.wavelength_nm, s.osc_strength]),
          itemStyle: { color: '#d97706' },
        },
      ],
    })
  } else if (props.kind === 'ir' && props.freqs && props.intensities) {
    chart.setOption({
      title: { text: '红外光谱', left: 'center', textStyle: { fontSize: 13 } },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'value', name: '波数 (cm⁻¹)', inverse: true, min: 4000, max: 0 },
      yAxis: { type: 'value', name: '强度 (km/mol)' },
      series: [
        {
          type: 'bar',
          barWidth: 6,
          data: props.freqs.map((f, i) => [f, props.intensities![i]]),
          itemStyle: { color: '#166534' },
        },
      ],
    })
  }
}

onMounted(render)
watch(() => props, render, { deep: true })

onBeforeUnmount(() => {
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.spectrum {
  background: #fafaf9;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
}

.label {
  font-size: 11px;
  font-weight: 600;
  color: var(--orange);
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.chart {
  height: 260px;
  width: 100%;
}

.thermo {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.thermo-item {
  background: var(--green-bg);
  border: 1px solid var(--green-border);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 12px;
  display: flex;
  gap: 6px;
}
.t-key {
  color: var(--text-secondary);
}
.t-val {
  font-weight: 600;
  color: var(--green-text);
}

.state-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 10px;
  font-size: 12px;
}
.state-table th,
.state-table td {
  text-align: center;
  padding: 6px;
  border-bottom: 1px solid var(--border);
}
.state-table th {
  color: var(--text-secondary);
  font-weight: 600;
}
</style>
