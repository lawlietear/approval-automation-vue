<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const value = defineModel<string>({ required: true })
const props = defineProps<{ options: string[]; disabled?: boolean }>()
const options = computed(() => [...new Set(props.options)])
const trigger = ref<HTMLButtonElement>()
const panel = ref<HTMLElement>()
const open = ref(false)
const active = ref(0)
const position = ref({ left: '0px', top: '0px', width: '340px', maxHeight: '320px' })
const listId = 'business-type-options'

function place() {
  if (!open.value || !trigger.value) return
  const rect = trigger.value.getBoundingClientRect()
  const width = Math.min(Math.max(rect.width, 340), window.innerWidth - 24)
  const below = window.innerHeight - rect.bottom - 16
  const above = rect.top - 16
  const useAbove = below < 200 && above > below
  const height = Math.min(320, Math.max(80, useAbove ? above : below))
  position.value = {
    left: `${Math.max(12, Math.min(rect.right - width, window.innerWidth - width - 12))}px`,
    top: `${useAbove ? Math.max(12, rect.top - 6 - Math.min(panel.value?.offsetHeight || height, height)) : rect.bottom + 6}px`,
    width: `${width}px`, maxHeight: `${height}px`,
  }
}
async function reveal() {
  if (props.disabled || !options.value.length) return
  active.value = Math.max(0, options.value.indexOf(value.value))
  open.value = true
  place()
  await nextTick()
  place()
  scrollActive()
}
function close() { open.value = false }
function select(index: number) {
  if (props.disabled || !open.value) return
  const option = options.value[index]
  if (option === undefined) return
  value.value = option
  close()
  trigger.value?.focus({ preventScroll: true })
}
function scrollActive() {
  panel.value?.querySelector(`#${listId}-${active.value}`)?.scrollIntoView({ block: 'nearest' })
}
async function keydown(event: KeyboardEvent) {
  if (!['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'Enter', ' ', 'Escape'].includes(event.key)) return
  if (event.key === 'Escape') { if (open.value) { event.preventDefault(); close() }; return }
  event.preventDefault()
  if (!open.value) { await reveal(); return }
  if (event.key === 'Enter' || event.key === ' ') { select(active.value); return }
  const delta = { ArrowDown: 2, ArrowUp: -2, ArrowLeft: -1, ArrowRight: 1 }[event.key] || 0
  active.value = event.key === 'Home' ? 0 : event.key === 'End' ? options.value.length - 1
    : Math.max(0, Math.min(options.value.length - 1, active.value + delta))
  await nextTick()
  scrollActive()
}
function outside(event: Event) {
  const target = event.target as Node
  if (!trigger.value?.contains(target) && !panel.value?.contains(target)) close()
}
watch(() => props.disabled, disabled => { if (disabled) close() })
watch(options, close)
onMounted(() => {
  document.addEventListener('pointerdown', outside)
  document.addEventListener('focusin', outside)
  window.addEventListener('resize', place)
  window.addEventListener('scroll', place, true)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outside)
  document.removeEventListener('focusin', outside)
  window.removeEventListener('resize', place)
  window.removeEventListener('scroll', place, true)
})
</script>

<template>
  <button ref="trigger" class="business-trigger" :class="{ expanded: open }" type="button"
    role="combobox" aria-label="业务类型" aria-haspopup="listbox" :aria-expanded="open"
    :aria-controls="open ? listId : undefined" :aria-activedescendant="open ? `${listId}-${active}` : undefined"
    :disabled="disabled || !options.length" @click="open ? close() : reveal()" @keydown="keydown">
    <span>{{ options.length ? value || '选择业务类型' : '暂无业务类型' }}</span>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
  </button>
  <Teleport to="body">
    <div v-if="open" ref="panel" class="business-popover" :style="position">
      <div class="business-heading"><span>选择业务类型</span><small>{{ options.length }} 项</small></div>
      <div :id="listId" class="business-grid" role="listbox" aria-label="业务类型选项">
        <div v-for="(option, index) in options" :id="`${listId}-${index}`" :key="option" role="option"
          :aria-selected="value === option" class="business-option" :class="{ selected: value === option, focused: active === index }"
          @pointerdown.prevent @click="select(index)" @pointermove="active = index">
          <span>{{ option }}</span>
          <svg v-if="value === option" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.business-trigger { width:100%; min-height:32px; display:flex; align-items:center; justify-content:space-between; gap:8px; padding:5px 9px; border:1px solid var(--border); border-radius:6px; background:var(--bg); color:var(--text); font:inherit; font-size:14px; text-align:left; cursor:pointer; transition:border-color .15s, box-shadow .15s; }
.business-trigger span { overflow-wrap:anywhere; }
.business-trigger:hover:not(:disabled), .business-trigger.expanded { border-color:var(--accent); }
.business-trigger:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.business-trigger:disabled { opacity:.5; cursor:not-allowed; }
svg { width:16px; height:16px; flex-shrink:0; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
.business-trigger svg { transition:transform .15s; }
.business-trigger.expanded svg { transform:rotate(180deg); }
.business-popover { position:fixed; z-index:100; display:flex; flex-direction:column; overflow:hidden; border:1px solid var(--border); border-radius:10px; background:var(--panel); color:var(--text); box-shadow:0 10px 28px #0002, 0 2px 6px #0001; animation:business-reveal .12s ease-out; }
.business-heading { display:flex; justify-content:space-between; align-items:center; padding:10px 13px; border-bottom:1px solid var(--border); font-size:12px; flex-shrink:0; }
.business-heading small { color:var(--text-secondary); font-size:11px; }
.business-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); overflow-y:auto; overscroll-behavior:contain; min-height:0; }
.business-option { min-height:36px; display:flex; justify-content:space-between; align-items:center; gap:6px; padding:9px 12px; border-bottom:1px solid var(--border); font-size:13px; line-height:1.5; cursor:pointer; overflow-wrap:anywhere; }
.business-option:nth-child(odd) { border-right:1px solid var(--border); }
.business-option.selected { color:var(--accent); background:var(--accent-glow); font-weight:600; }
.business-option.focused { box-shadow:inset 0 0 0 1px var(--accent); background:var(--accent-glow); }
@keyframes business-reveal { from { opacity:0; transform:translateY(-3px); } to { opacity:1; transform:translateY(0); } }
@media (prefers-reduced-motion:reduce) { .business-popover { animation:none; } .business-trigger, .business-trigger svg { transition:none; } }
</style>
