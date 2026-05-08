<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  logs: {time: string; type: 'ok' | 'error' | 'info'; msg: string}[]
  open: boolean
  dotType: 'active' | 'error' | 'idle'
}>()

const emit = defineEmits<{
  toggle: []
}>()

const latestLog = computed(() => {
  if (props.logs.length === 0) return 'waiting...'
  return props.logs[props.logs.length - 1].msg
})
</script>

<template>
  <div class="log-drawer" :class="{ collapsed: !open }">
    <div class="log-header" @click="emit('toggle')">
      <div class="log-header-left">
        <div class="log-dot" :class="dotType"></div>
        <span>logs</span>
        <span class="log-latest">{{ latestLog }}</span>
      </div>
      <div class="log-toggle">&#9662;</div>
    </div>
    <div class="log-body">
      <div
        v-for="(log, i) in logs"
        :key="i"
        class="log-line"
      >
        <span class="log-time">{{ log.time }}</span>
        <span class="log-tag" :class="log.type">{{ log.type === 'ok' ? 'ok' : log.type === 'error' ? 'err' : 'info' }}</span>
        <span class="log-msg">{{ log.msg }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-drawer {
  border-top: 1px solid rgba(var(--text-rgb), 0.09);
  background: rgba(var(--card-rgb), 0.38);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  transition: all 0.3s ease, background 0.3s ease, border-color 0.3s ease;
  flex-shrink: 0;
}
.log-drawer.collapsed .log-body {
  max-height: 0;
  opacity: 0;
  padding: 0 24px;
}
.log-drawer.collapsed {
  background: rgba(var(--card-rgb), 0.25);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 24px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}
.log-header:hover { background: var(--accent-glow); }
.log-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}
.log-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--text-secondary);
}
.log-dot.active { background: var(--accent); }
.log-dot.error { background: var(--error); }
.log-latest {
  font-size: 11px;
  color: var(--text-tertiary);
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'JetBrains Mono', monospace;
}
.log-toggle {
  font-size: 12px;
  color: var(--text-secondary);
  transition: transform 0.3s ease;
}
.log-drawer.collapsed .log-toggle {
  transform: rotate(-90deg);
}
.log-body {
  max-height: 180px;
  overflow-y: auto;
  padding: 0 24px 14px;
  opacity: 1;
  transition: all 0.3s ease;
  font-family: 'JetBrains Mono', monospace;
}
.log-line {
  display: flex;
  gap: 10px;
  align-items: baseline;
  padding: 3px 0;
  font-size: 11px;
}
.log-time {
  color: var(--text-secondary);
  min-width: 56px;
  font-size: 10px;
}
.log-tag {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 600;
  flex-shrink: 0;
  text-transform: uppercase;
}
.log-tag.ok { background: rgba(34,197,94,0.1); color: var(--success); }
.log-tag.info { background: rgba(115,115,115,0.08); color: var(--text-tertiary); }
.log-tag.error { background: rgba(239,68,68,0.08); color: var(--error); }
.log-msg { color: var(--text-tertiary); }
</style>
