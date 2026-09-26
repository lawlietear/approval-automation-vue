<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import LeftPanel from './components/LeftPanel.vue'
import RightPanel from './components/RightPanel.vue'
import LogDrawer from './components/LogDrawer.vue'
import { defaultWorkflow, type DebugResult } from './workflow'

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
const isConnecting = ref(false)
const connectedEndpoint = ref('')
const stepIndex = ref(-1)
const view = ref<'empty' | 'loading' | 'data'>('empty')
const hasExtractedData = ref(false)
const pageSub = ref('从左侧连接浏览器，开始审批')
const isRunning = ref(false)
const workflow = ref(defaultWorkflow())
const debugResult = ref<DebugResult | null>(null)

// Data
const dataMap = ref<Record<string, string>>({})
const bizTypeOptions = ref<string[]>([])

// Logs
const logs = ref<{time: string; type: 'ok' | 'error' | 'info'; msg: string}[]>([])
const logDrawerOpen = ref(false)
const logDotType = ref<'active' | 'error' | 'idle'>('idle')

let logWriteFailed = false
const addLog = (msg: string, type: 'ok' | 'error' | 'info' = 'info', persist = true) => {
  const time = new Date().toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit', second:'2-digit'})
  logs.value.push({time, type, msg})
  logDotType.value = type === 'error' ? 'error' : 'active'
  if (type === 'error') logDrawerOpen.value = true
  if (persist) void invoke('append_ui_log', { level: type, message: msg }).catch(e => {
    if (!logWriteFailed) {
      logWriteFailed = true
      addLog(String(e), 'error', false)
    }
  })
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
const handleConnect = (endpoint: string) => {
  connectedEndpoint.value = endpoint
  isConnected.value = !!endpoint
  stepIndex.value = endpoint ? 0 : -1
  pageSub.value = endpoint ? '连接已验证，请打开审批页面；浏览器重启后需重新连接' : '请连接浏览器后开始审批'
  if (endpoint) addLog('Chrome 调试连接验证通过，尚未执行审批', 'ok')
}

const handleStart = async (payload: { system: 'core' | 'oa'; qty: string; bizType: string; inspectOnly?: boolean }) => {
  if (!isConnected.value || isRunning.value) return
  clearTimers()
  isRunning.value = true
  stepIndex.value = 1
  view.value = 'loading'
  pageSub.value = workflow.value.debug_enabled || payload.inspectOnly ? '安全检查中：不会点击或登记' : `extracting ${payload.system === 'core' ? 'core' : 'oa'} data...`
  addLog(pageSub.value, 'info')

  try {
    await invoke('start_approval', {
      cdpEndpoint: connectedEndpoint.value,
      configPath: CONFIG_PATH,
      qty: payload.qty,
      bizType: payload.bizType,
      oaType: payload.system === 'core' ? 'old' : 'new',
      testMode: false,
      inspectOnly: payload.inspectOnly || false,
      safeDebug: workflow.value.debug_enabled,
    })
  } catch (e: any) {
    addLog(`start failed: ${e}`, 'error')
    isRunning.value = false
    stepIndex.value = isConnected.value ? 0 : -1
    view.value = hasExtractedData.value ? 'data' : 'empty'
    pageSub.value = '本次启动失败，请查看日志；尚未启动审批流程。'
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
  // Vue DOM 已渲染，确保 loading 动画至少显示 1.2 秒后再淡出
  const loader = document.getElementById('loader')
  if (loader) {
    setTimeout(() => {
      loader.classList.add('hide')
      setTimeout(() => loader.remove(), 500)
    }, 1200)
  }

  unlisteners.push(await listen('approval:log', (e: any) => {
    addLog(e.payload.msg, e.payload.level || 'info', false)
  }))

  unlisteners.push(await listen('approval:data_extracted', (e: any) => {
    dataMap.value = e.payload.data || {}
    hasExtractedData.value = true
    stepIndex.value = 2
    view.value = 'data'
    pageSub.value = '已提取，正在登记…'
    addLog('data extraction complete', 'ok')
  }))

  unlisteners.push(await listen('approval:debug_result', (e: any) => {
    debugResult.value = e.payload
    if (e.payload.records?.length) {
      dataMap.value = e.payload.records[0]
      hasExtractedData.value = true
      view.value = 'data'
    } else { view.value = hasExtractedData.value ? 'data' : 'empty' }
    stepIndex.value = 1
    pageSub.value = '调试完成：未发送点击、未审批、未登记。检查结果见设置中的“调试与部门”。'
    addLog(pageSub.value, 'info')
  }))

  unlisteners.push(await listen('approval:submit_success', () => {
    addLog('approval submitted successfully', 'ok')
  }))

  unlisteners.push(await listen('approval:all_done', (e: any) => {
    stepIndex.value = 4
    isRunning.value = false
    const result = e.payload
    if (result.cancelled) {
      pageSub.value = '流程已取消，请核对已登记记录'
    } else if (result.registration_enabled === false) {
      pageSub.value = '审批处理完成，登记通道已关闭'
    } else if (result.success_count === result.count) {
      pageSub.value = `登记完成：${result.success_count} 条`
      startCountdown()
    } else {
      pageSub.value = `部分登记未完成：${result.success_count}/${result.count} 条全部通道成功，请查看日志`
      addLog(pageSub.value, 'error')
    }
  }))

  unlisteners.push(await listen('approval:error', (e: any) => {
    addLog(e.payload.msg, 'error', false)
    isRunning.value = false
    if (view.value === 'loading') view.value = hasExtractedData.value ? 'data' : 'empty'
    pageSub.value = '本次操作未完成，请查看日志；不要自动重试审批。'
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
        :is-connecting="isConnecting"
        :view="view"
        :biz-type-options="bizTypeOptions"
        :debug-result="debugResult"
        @workflow-changed="workflow = $event"
        @toggle-theme="toggleTheme"
        @connect="handleConnect"
        @browser-busy="isConnecting = $event"
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
@media (max-width:680px) { .workspace { display:block; overflow-y:auto; } }
</style>
