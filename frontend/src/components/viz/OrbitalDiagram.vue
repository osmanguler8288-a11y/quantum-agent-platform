<template>
  <div class="orbital">
    <div class="label">ORBITAL ENERGY DIAGRAM</div>
    <svg :width="W" :height="H" :viewBox="`0 0 ${W} ${H}`">
      <!-- 能量轴 -->
      <line :x1="0" :y1="10" :x2="0" :y2="H - 20" stroke="#d6d3d1" stroke-width="1" />
      <text x="6" y="14" font-size="10" fill="#78716c">E (eV)</text>

      <g v-for="orb in orbitals" :key="orb.idx">
        <!-- 能级线 -->
        <line
          :x1="0"
          :x2="W - 40"
          :y1="yOf(orb.energy_eV)"
          :y2="yOf(orb.energy_eV)"
          :stroke="lineColor(orb)"
          :stroke-width="orb.occ ? 2.5 : 1.5"
          :stroke-dasharray="orb.occ ? '' : '4 3'"
        />
        <!-- 轨道标签 -->
        <text
          :x="orb.occ ? 4 : W - 44"
          :y="yOf(orb.energy_eV) - 4"
          font-size="10"
          :fill="labelColor(orb)"
          :text-anchor="orb.occ ? 'start' : 'end'"
        >
          #{{ orb.idx }}{{ tagOf(orb) }}
        </text>
      </g>
    </svg>
    <div class="legend">
      <span><span class="dot solid"></span> 占据轨道</span>
      <span><span class="dot dashed"></span> 空轨道</span>
      <span><span class="dot homo"></span> HOMO/LUMO</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Orbital } from '@/types'

const props = defineProps<{ orbitals: Orbital[]; homoE: number; lumoE: number }>()

const W = 520
const H = 300

const energies = computed(() => props.orbitals.map((o) => o.energy_eV))
const minE = computed(() => Math.min(...energies.value) - 1.5)
const maxE = computed(() => Math.max(...energies.value) + 1.5)

function yOf(e: number): number {
  const range = maxE.value - minE.value
  return 20 + ((maxE.value - e) / range) * (H - 40)
}

function isHomo(o: Orbital): boolean {
  return Math.abs(o.energy_eV - props.homoE) < 1e-6
}
function isLumo(o: Orbital): boolean {
  return Math.abs(o.energy_eV - props.lumoE) < 1e-6
}

function lineColor(o: Orbital): string {
  if (isHomo(o) || isLumo(o)) return '#d97706'
  return o.occ ? '#44403c' : '#a8a29e'
}

function labelColor(o: Orbital): string {
  if (isHomo(o) || isLumo(o)) return '#d97706'
  return o.occ ? '#44403c' : '#a8a29e'
}

function tagOf(o: Orbital): string {
  if (isHomo(o)) return ' (HOMO)'
  if (isLumo(o)) return ' (LUMO)'
  return ''
}
</script>

<style scoped>
.orbital {
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

svg {
  display: block;
  width: 100%;
  height: auto;
}

.legend {
  display: flex;
  gap: 16px;
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 8px;
}
.legend span {
  display: flex;
  align-items: center;
  gap: 4px;
}
.dot {
  width: 14px;
  height: 2px;
  display: inline-block;
}
.dot.solid {
  background: #44403c;
  height: 3px;
}
.dot.dashed {
  background: repeating-linear-gradient(90deg, #a8a29e 0 4px, transparent 4px 7px);
}
.dot.homo {
  background: #d97706;
  height: 3px;
}
</style>
