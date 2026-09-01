<template>
  <div class="result-viz">
    <template v-if="viz.type === 'homo_lumo'">
      <NumberCard :label="'HOMO-LUMO gap'" :value="viz.gap_eV" :unit="'eV'" />
      <OrbitalDiagram :orbitals="viz.orbitals" :homo-e="viz.homo_e" :lumo-e="viz.lumo_e" />
    </template>

    <template v-else-if="viz.type === 'dipole'">
      <NumberCard label="偶极矩" :value="viz.components.tot" unit="Debye" />
    </template>

    <template v-else-if="viz.type === 'tddft'">
      <SpectrumPlot kind="absorption" :states="viz.states" />
    </template>

    <template v-else-if="viz.type === 'freq'">
      <SpectrumPlot kind="ir" :freqs="viz.freqs" :intensities="viz.intensities" :thermo="viz.thermo" />
    </template>

    <template v-else-if="viz.type === 'structure'">
      <Molecule3D :atoms="viz.atoms" />
    </template>

    <template v-else-if="viz.type === 'energy'">
      <NumberCard :label="viz.label" :value="viz.value" :unit="viz.unit" />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { VizResult } from '@/types'
import NumberCard from './NumberCard.vue'
import OrbitalDiagram from './OrbitalDiagram.vue'
import SpectrumPlot from './SpectrumPlot.vue'
import Molecule3D from './Molecule3D.vue'

defineProps<{ viz: VizResult }>()
</script>

<style scoped>
.result-viz {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
