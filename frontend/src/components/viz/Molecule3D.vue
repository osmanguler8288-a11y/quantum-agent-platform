<template>
  <div class="mol">
    <div class="label">MOLECULAR STRUCTURE</div>
    <div ref="viewerEl" class="viewer"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import type { Atom } from '@/types'
import * as $3Dmol from '3dmol'

const props = defineProps<{ atoms: Atom[] }>()

const viewerEl = ref<HTMLElement>()
let viewer: any = null

function toXyz(atoms: Atom[]): string {
  return (
    `${atoms.length}\n\n` +
    atoms.map((a) => `${a.symbol} ${a.x.toFixed(4)} ${a.y.toFixed(4)} ${a.z.toFixed(4)}`).join('\n')
  )
}

function render() {
  if (!viewerEl.value || !props.atoms.length) return

  if (!viewer) {
    viewer = $3Dmol.createViewer(viewerEl.value, { backgroundColor: 'white' })
  }

  viewer.removeAllModels()
  viewer.addModel(toXyz(props.atoms), 'xyz')
  viewer.setStyle({}, { stick: { radius: 0.12 }, sphere: { scale: 0.28 } })
  viewer.zoomTo()
  viewer.render()
}

onMounted(render)
watch(() => props.atoms, render, { deep: true })

onBeforeUnmount(() => {
  viewer?.removeAllModels()
  viewerEl.value && (viewerEl.value.innerHTML = '')
  viewer = null
})
</script>

<style scoped>
.mol {
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

.viewer {
  width: 100%;
  height: 300px;
  position: relative;
}
</style>
