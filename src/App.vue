<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import LeftPanel from './components/LeftPanel.vue'
import RightPanel from './components/RightPanel.vue'
import LogDrawer from './components/LogDrawer.vue'

const CONFIG_PATH = 'src-tauri/python/config.json'

// Theme
const isDark = ref(false)
document.documentElement.setAttribute('data-theme', isDark.value ? '' : 'light')
const toggleTheme = () => {
  isDark.value = !isDark.value
  document.documentElement.setAttribute('data-theme', isDark.value ? '' : 'light')
}

// Connection & Flow
const isConnected = ref(false)
const stepIndex = ref(-1)
const view = ref<'empty' | 'loading' | 'data'>('empty')
const hasExtractedData = ref(false)
const pageSub = ref('connect chrome to begin')
const isRunning = ref(false)

// Data
const dataMap = ref<Record<string, string>>({})
const bizTypeOptions = ref<string[]>([])

// Logs
const logs = ref<{time: string; type: 'ok' | 'error' | 'info'; msg: string}[]>([])
const logDrawerOpen = ref(false)
const logDotType = ref<'active' | 'error' | 'idle'>('idle')

const addLog = (msg: string, type: 'ok' | 'error' | 'info' = 'info') => {
  const time = new Date().toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit', second:'2-digit'})
  logs.value.push({time, type, msg})
  logDotType.value = type === 'error' ? 'error' : 'active'
  if (type === 'error') logDrawerOpen.value = true
}

// Timers
let autoResetTimer: ReturnType<typeof setTimeout> | null = null
let countdownTimer: ReturnType<typeof setInterval> | null = null
const countdown = ref(0)

const clearTimers = () => {
  if (autoResetTimer) { clearTimeout(autoResetTimer); autoResetTimer = null }
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
  countdown.value = 0
}

const startCountdown = () => {
  clearTimers()
  countdown.value = 30
  countdownTimer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
    }
  }, 1000)
  autoResetTimer = setTimeout(() => {
    view.value = 'empty'
    pageSub.value = 'data retained. switch back anytime.'
    clearTimers()
  }, 30000)
}

// Actions
const handleConnect = async () => {
  if (isRunning.value) return
  try {
    await invoke('connect_chrome', { cdpEndpoint: 'http://localhost:9222' })
    const wasConnected = isConnected.value
    isConnected.value = true
    stepIndex.value = 0
    pageSub.value = 'waiting...'
    if (!wasConnected) {
      addLog('chrome connected', 'ok')
      addLog('page title verified', 'ok')
    } else {
      addLog('chrome reconnected', 'ok')
    }
  } catch (e: any) {
    addLog(`connect failed: ${e}`, 'error')
  }
}

const handleStart = async (payload: { system: 'core' | 'oa'; qty: string; bizType: string }) => {
  if (!isConnected.value || isRunning.value) return
  clearTimers()
  isRunning.value = true
  stepIndex.value = 1
  view.value = 'loading'
  pageSub.value = `extracting ${payload.system === 'core' ? 'core' : 'oa'} data...`
  addLog(`start ${payload.system === 'core' ? 'core system' : 'oa system'} approval`, 'info')

  try {
    await invoke('start_approval', {
      cdpEndpoint: 'http://localhost:9222',
      configPath: CONFIG_PATH,
      qty: payload.qty,
      bizType: payload.bizType,
      oaType: payload.system === 'core' ? 'old' : 'new',
      testMode: false,
    })
  } catch (e: any) {
    addLog(`start failed: ${e}`, 'error')
    isRunning.value = false
    stepIndex.value = isConnected.value ? 0 : -1
    if (!hasExtractedData.value) {
      view.value = 'empty'
    }
  }
}

const handleCancel = async () => {
  clearTimers()
  try {
    await invoke('cancel_approval')
  } catch (e: any) {
    addLog(`cancel failed: ${e}`, 'error')
  }
  isRunning.value = false
  stepIndex.value = isConnected.value ? 0 : -1
  pageSub.value = isConnected.value ? 'waiting...' : 'connect chrome to begin'
  if (!hasExtractedData.value) {
    view.value = 'empty'
  }
  addLog('operation cancelled', 'info')
}

const handleSwitchView = (v: 'empty' | 'data') => {
  if (!hasExtractedData.value) return
  clearTimers()
  view.value = v
  pageSub.value = v === 'empty' ? 'data retained. switch back anytime.' : 'showing current approval detail'
}

// Event listeners
let unlisteners: UnlistenFn[] = []

onMounted(async () => {
  unlisteners.push(await listen('approval:log', (e: any) => {
    addLog(e.payload.msg, e.payload.level || 'info')
  }))

  unlisteners.push(await listen('approval:data_extracted', (e: any) => {
    dataMap.value = e.payload.data || {}
    hasExtractedData.value = true
    stepIndex.value = 2
    view.value = 'data'
    pageSub.value = 'extracted. submitting...'
    addLog('data extraction complete', 'ok')
  }))

  unlisteners.push(await listen('approval:submit_success', () => {
    addLog('approval submitted successfully', 'ok')
  }))

  unlisteners.push(await listen('approval:all_done', () => {
    stepIndex.value = 4
    isRunning.value = false
    pageSub.value = 'approval submitted'
    startCountdown()
  }))

  unlisteners.push(await listen('approval:error', (e: any) => {
    addLog(e.payload.msg, 'error')
    isRunning.value = false
    stepIndex.value = isConnected.value ? 0 : -1
  }))

  unlisteners.push(await listen('approval:finished', () => {
    isRunning.value = false
  }))

  try {
    addLog('loading config...', 'info')
    const config = await invoke('get_config', { configPath: CONFIG_PATH }) as any
    addLog(`config raw keys: ${Object.keys(config).join(', ')}`, 'info')
    const opts = config.approval?.biz_type_options
    if (Array.isArray(opts)) {
      bizTypeOptions.value = opts
      addLog(`config loaded, ${opts.length} biz types`, 'ok')
    } else {
      addLog(`config loaded but biz_type_options missing. approval keys: ${Object.keys(config.approval || {}).join(', ')}`, 'error')
    }
  } catch (e: any) {
    addLog(`load config failed: ${e}`, 'error')
  }
})

onUnmounted(() => {
  clearTimers()
  unlisteners.forEach(fn => fn())
})
</script>

<template>
  <div class="app">
    <div class="workspace">
      <LeftPanel
        :is-dark="isDark"
        :is-connected="isConnected"
        :step-index="stepIndex"
        :has-extracted-data="hasExtractedData"
        :countdown="countdown"
        :is-running="isRunning"
        :view="view"
        :biz-type-options="bizTypeOptions"
        @toggle-theme="toggleTheme"
        @connect="handleConnect"
        @start="handleStart"
        @cancel="handleCancel"
        @switch-view="handleSwitchView"
      />
      <RightPanel
        :view="view"
        :data-map="dataMap"
        :page-sub="pageSub"
      />
    </div>
    <LogDrawer
      :logs="logs"
      :open="logDrawerOpen"
      :dot-type="logDotType"
      @toggle="logDrawerOpen = !logDrawerOpen"
    />
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
.workspace {
  display: flex;
  flex: 1;
  overflow: hidden;
}
</style>
