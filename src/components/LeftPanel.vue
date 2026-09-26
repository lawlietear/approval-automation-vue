<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import PushSettings from './PushSettings.vue'
import BrowserConnection from './BrowserConnection.vue'
import SoftwareUpdate from './SoftwareUpdate.vue'
import WorkflowSettingsPanel from './WorkflowSettings.vue'
import { defaultWorkflow, type WorkflowSettings, type DebugResult } from '../workflow'

const props = defineProps<{
  isDark: boolean
  isConnected: boolean
  isConnecting: boolean
  stepIndex: number
  hasExtractedData: boolean
  countdown: number
  isRunning: boolean
  view: 'empty' | 'loading' | 'data'
  bizTypeOptions: string[]
  debugResult: DebugResult | null
}>()

const emit = defineEmits<{
  toggleTheme: []
  connect: [endpoint: string]
  browserBusy: [value: boolean]
  start: [payload: { system: 'core' | 'oa'; qty: string; bizType: string; inspectOnly?: boolean }]
  workflowChanged: [value: WorkflowSettings]
  cancel: []
  switchView: [view: 'empty' | 'data']
}>()

const qty = ref('1')
const bizType = ref('金融不良资产')
const activeSystem = ref<'core' | 'oa' | null>(null)
watch(() => props.isRunning, running => { if (!running) activeSystem.value = null })

const settingsBusy = ref(true)
const updateBusy = ref(false)
const workflowBusy = ref(true)
const workflow = ref(defaultWorkflow())
const workflowMessage = ref('')
const sysDisabled = computed(() => !props.isConnected || props.isConnecting || props.isRunning || (!workflow.value.debug_enabled && settingsBusy.value) || updateBusy.value || workflowBusy.value)
function applyWorkflow(value: WorkflowSettings) { workflow.value = value; emit('workflowChanged', value) }
async function changeDepartment(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  workflowBusy.value = true
  try {
    const next = { ...workflow.value, department_id: value }
    await invoke('save_workflow_settings', { settings: next })
    applyWorkflow(next)
    workflowMessage.value = ''
  } catch (error) { workflowMessage.value = String(error); (event.target as HTMLSelectElement).value = workflow.value.department_id }
  finally { workflowBusy.value = false }
}
function inspectDepartments() {
  if (!props.isConnected || props.isRunning || props.isConnecting || updateBusy.value) return
  emit('start', { system: 'core', qty: qty.value, bizType: bizType.value, inspectOnly: true })
}
const settingsDialog = ref<HTMLDialogElement>()
const settingsTab = ref('registration')
const summary = ref('正在读取登记状态…')
const appInfo = ref({ version: '', settings_directory: '' })
onMounted(async () => {
  try { appInfo.value = await invoke('get_app_info') } catch { /* Settings panels display detailed load failures. */ }
})
function openSettings(tab = 'registration') {
  settingsTab.value = tab
  settingsDialog.value?.showModal()
}

const handleSystem = (system: 'core' | 'oa') => {
  if (sysDisabled.value || activeSystem.value || (workflow.value.debug_enabled && system === 'oa')) return
  activeSystem.value = system
  emit('start', { system, qty: qty.value, bizType: bizType.value })
}

</script>

<template>
  <div class="sidebar">
    <div class="logo">
      <div>自动化审批 <span>工作台</span></div>
      <div class="header-tools"><button class="settings-top" @click="openSettings()">设置</button><button class="theme-btn" @click="emit('toggleTheme')" title="切换主题">
        <span>{{ isDark ? '☼' : '☾' }}</span>
      </button></div>
    </div>

    <div class="steps">
      <div class="step" :class="{ completed: stepIndex > 0, active: stepIndex === 0 }">
        <div class="step-icon">{{ stepIndex > 0 ? '✓' : '1' }}</div>
        <div class="step-label">连接</div>
      </div>
      <div class="step-line" :class="{ completed: stepIndex >= 1 }"></div>
      <div class="step" :class="{ completed: stepIndex > 1, active: stepIndex === 1 }">
        <div class="step-icon">{{ stepIndex > 1 ? '✓' : '2' }}</div>
        <div class="step-label">提取</div>
      </div>
      <div class="step-line" :class="{ completed: stepIndex >= 2 }"></div>
      <div class="step" :class="{ completed: stepIndex > 2, active: stepIndex === 2 }">
        <div class="step-icon">{{ stepIndex > 2 ? '✓' : '3' }}</div>
        <div class="step-label">登记</div>
      </div>
      <div class="step-line" :class="{ completed: stepIndex >= 3 }"></div>
      <div class="step" :class="{ completed: stepIndex > 3, active: stepIndex === 3 }">
        <div class="step-icon">{{ stepIndex > 3 ? '✓' : '4' }}</div>
        <div class="step-label">完成</div>
      </div>
    </div>

    <BrowserConnection :is-running="isRunning || updateBusy" @connected="emit('connect', $event)" @busy="emit('browserBusy', $event)" @settings="openSettings('browser')" />

    <div class="param-card">
      <div class="param-section quantity-section">
        <div class="param-label">数量</div>
        <div class="qty-row">
          <select class="qty-input" aria-label="审批数量" v-model="qty"><option v-for="n in 10" :key="n" :value="String(n)">{{ n }}</option></select>
        </div>
      </div>
      <div class="param-section">
        <div class="param-label">业务类型</div>
        <select class="biz-select" aria-label="业务类型" v-model="bizType">
          <option v-for="opt in bizTypeOptions" :key="opt">{{ opt }}</option>
        </select>
      </div>
    </div>

    <div class="action-card">
      <div class="action-heading">{{ workflow.debug_enabled ? '安全调试 · 不审批不登记' : '审批并登记' }}<span>{{ isRunning ? '正在处理，请勿重复操作' : workflow.debug_enabled ? '仅提取信息及可点击性检查，不发送点击' : '核对当前浏览器页面，再选择对应系统' }}</span></div>
      <div class="btn-row">
        <button
          class="btn primary"
          :disabled="sysDisabled"
          @click="handleSystem('core')"
          :class="{ processing: isRunning && activeSystem === 'core' }"
          :aria-busy="isRunning && activeSystem === 'core'"
        ><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h6M9 11h6m-6 4h2m3 0h1M10 21v-3h4v3"/></svg><span>核心业务系统</span><span class="action-arrow" aria-hidden="true">↗</span></button>
        <button
          class="btn primary"
          :disabled="sysDisabled || workflow.debug_enabled"
          @click="handleSystem('oa')"
          :class="{ processing: isRunning && activeSystem === 'oa' }"
          :aria-busy="isRunning && activeSystem === 'oa'"
        ><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Zm0 0v6h6M8 14l3 3 5-5"/></svg><span>OA 系统</span><span class="action-arrow" aria-hidden="true">↗</span></button>
      </div>
      <label v-if="workflow.show_department" class="home-department">部门选择
        <select aria-label="首页部门选择" :value="workflow.department_id" :disabled="isRunning || workflowBusy || updateBusy" @change="changeDepartment">
          <option value="">沿用原配置</option><option v-for="item in workflow.departments" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </label>
      <p v-if="workflowMessage" role="alert">{{ workflowMessage }}</p>
    </div>

    <div class="registration-summary"><span>登记去向</span><p>{{ summary }}</p><p v-if="settingsBusy" class="pending">请先在设置中完成配置并保存</p></div>

    <Teleport to="body">
      <dialog ref="settingsDialog" class="settings-dialog" aria-labelledby="settings-title" @cancel="updateBusy && $event.preventDefault()">
        <header><div><span class="eyebrow">仅在需要时调整</span><h2 id="settings-title">设置</h2></div><button class="btn" :disabled="updateBusy" @click="settingsDialog?.close()">返回工作台</button></header>
        <nav aria-label="设置分类"><button v-for="[key, label] in [['registration', '数据登记'], ['browser', '浏览器'], ['workflow', '调试与部门'], ['update', '软件更新']]" :key="key" class="btn" :class="{ selected: settingsTab === key }" :aria-pressed="settingsTab === key" @click="settingsTab = key">{{ label }}</button></nav>
        <div class="settings-content">
          <div v-show="settingsTab === 'registration'"><PushSettings :is-running="isRunning || updateBusy" @busy="settingsBusy = $event" @summary="summary = $event" /></div>
          <div v-show="settingsTab === 'browser'" id="browser-settings-pane"></div>
          <div v-show="settingsTab === 'workflow'"><WorkflowSettingsPanel :is-running="isRunning || updateBusy" :can-inspect="isConnected && !isConnecting && !isRunning && !updateBusy" :saved="workflow" :result="debugResult" @busy="workflowBusy = $event" @changed="applyWorkflow" @inspect="inspectDepartments" /></div>
          <div v-show="settingsTab === 'update'"><SoftwareUpdate :disabled="isRunning || isConnecting || settingsBusy" @busy="updateBusy = $event" /></div>
        </div>
        <footer><strong>配置仅保存在当前电脑，软件升级不会覆盖。</strong><span>v{{ appInfo.version }} · {{ appInfo.settings_directory }}</span></footer>
      </dialog>
    </Teleport>

    <div class="view-toggle" v-show="hasExtractedData">
      <div class="view-toggle-label">预览<span v-if="countdown > 0">{{ countdown }} 秒后自动隐藏</span></div>
      <div class="view-toggle-btns">
        <button
          class="btn"
          :class="{ 'active-state': view === 'data' }"
          @click="emit('switchView', 'data')"
        >查看数据</button>
        <button
          class="btn"
          :class="{ 'active-state': view === 'empty' }"
          @click="emit('switchView', 'empty')"
        >隐藏数据</button>
      </div>
    </div>

    <div class="cancel-card" v-show="isRunning">
      <button
        class="btn cancel-btn"
        :disabled="!isRunning"
        @click="emit('cancel')"
      >取消</button>
    </div>
  </div>
</template>

<style scoped>
.home-department { display:flex; gap:12px; align-items:center; font-size:12px; margin-top:8px; }
.home-department select { min-width:0; flex:1; padding:7px; border:1px solid var(--border); border-radius:6px; color:var(--text); background:var(--bg); }
.settings-dialog nav { flex-wrap:wrap; }
.registration-summary { padding:4px 0; font-size:11px; color:var(--text-secondary); }
.registration-summary p { margin-top:6px; line-height:1.6; }
.pending { color:var(--accent); }
.header-tools { display:flex; align-items:center; gap:6px; }
.settings-top { font:inherit; font-size:12px; padding:7px 9px; border:1px solid var(--border); border-radius:6px; background:var(--panel); color:var(--accent); cursor:pointer; }
.settings-dialog { margin:auto; padding:0; width:min(760px, calc(100vw - 32px)); max-height:calc(100vh - 32px); border:1px solid var(--border); border-radius:14px; background:var(--panel); color:var(--text); box-shadow:0 24px 80px #0005; }
.settings-dialog[open] { display:flex; flex-direction:column; }
.settings-dialog::backdrop { background:#15130f88; }
.settings-dialog header { display:flex; align-items:center; justify-content:space-between; padding:22px 26px; border-bottom:1px solid var(--border); }
.settings-dialog h2 { font-size:24px; margin-top:5px; }
.eyebrow { font-size:11px; color:var(--accent); }
.settings-dialog nav { display:flex; gap:8px; padding:16px 26px 0; }
.settings-dialog nav .selected { color:var(--accent); border-color:var(--accent); background:var(--accent-glow); }
.settings-content { padding:22px 26px; overflow:auto; min-height:240px; }
.settings-dialog footer { padding:16px 26px; border-top:1px solid var(--border); font-size:11px; color:var(--text-secondary); line-height:1.6; overflow-wrap:anywhere; }
.settings-dialog footer span { display:block; margin-top:5px; }
.sidebar {
  width: 52%;
  min-width: 340px;
  background: var(--panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px clamp(20px, 3vw, 42px);
  gap: 10px;
  transition: background 0.3s ease, border-color 0.3s ease;
  flex-shrink: 0;
  overflow-y: auto;
}
.logo {
  font-family: 'JetBrains Mono', monospace;
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.02em;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.logo span {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-secondary);
  letter-spacing: 0.05em;
}
.theme-btn {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all 0.2s ease;
}
.theme-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

/* Steps */
.steps {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 0;
  background: rgba(var(--card-rgb), 0.38);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 0;
  box-shadow: inset 0 1px 0 0 rgba(255,255,255,0.04);
  border-radius: 8px;
  transition: background 0.3s ease, border-color 0.3s ease;
}
.step {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.step-icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  background: var(--border);
  color: var(--text-secondary);
  transition: all 0.3s ease;
}
.step.completed .step-icon {
  background: #14b8a6;
  color: var(--bg);
  animation: check-pop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.step.active .step-icon {
  background: #14b8a6;
  color: #fff;
  box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.2);
  animation: pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.step-label {
  font-size: 10px;
  color: var(--text-secondary);
  white-space: nowrap;
  font-weight: 500;
  letter-spacing: 0.05em;
  transition: color 0.3s ease;
}
.step.completed .step-label { color: var(--text-tertiary); }
.step.active .step-label { color: #14b8a6; }
.step-line {
  flex: 1;
  height: 1.5px;
  background: var(--border);
  min-width: 12px;
  border-radius: 1px;
  transition: background 0.3s ease;
}
.step-line.completed {
  background: #14b8a6;
  transform-origin: left;
  animation: charge 0.5s ease-out forwards;
}

/* Status */
.status-card {
  background: rgba(var(--card-rgb), 0.38);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(var(--text-rgb), 0.09);
  box-shadow: inset 0 1px 0 0 rgba(255,255,255,0.04);
  border-radius: 8px;
  padding: 14px;
  transition: background 0.3s ease, border-color 0.3s ease;
}
.status-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-secondary);
  position: relative;
}
.status-dot.pulse {
  background: var(--success);
}
.status-dot.pulse::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1.5px solid var(--success-glow);
  animation: ripple 2s ease-out infinite;
}
@keyframes ripple {
  0% { transform: scale(1); opacity: 1; }
  100% { transform: scale(1.8); opacity: 0; }
}
.status-label { font-size: 12px; color: var(--text-secondary); font-weight: 400; }
.status-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 16px;
  color: var(--text-secondary);
  font-weight: 700;
}
.status-title.connected { color: var(--success); }
.status-sub { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.status-connect-btn {
  margin-top: 10px;
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-weight: 500;
}
.status-connect-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-glow);
}
.status-connect-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* Params */
.param-card {
  background: rgba(var(--card-rgb), 0.38);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(var(--text-rgb), 0.09);
  box-shadow: inset 0 1px 0 0 rgba(255,255,255,0.04);
  border-radius: 8px;
  padding: 10px;
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  gap: 10px;
  transition: background 0.3s ease, border-color 0.3s ease;
}
.param-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.qty-row { display: flex; align-items: center; gap: 6px; }
.qty-btn {
  width: 36px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font-size: 14px;
  font-weight: 400;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
}
.qty-btn:hover { border-color: var(--accent); color: var(--accent); }
.qty-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.custom-label { font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
.qty-input {
  width: 58px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  padding: 2px 8px;
  font-size: 14px;
  color: var(--text);
  outline: none;
  transition: border-color 0.2s;
}
.qty-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
  animation: focus-breathe 2.5s ease-in-out infinite;
}

.biz-select {
  width: 100%;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  padding: 0 8px;
  font-size: 14px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text);
  outline: none;
  cursor: pointer;
  transition: border-color 0.2s;
}
.biz-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
  animation: focus-breathe 2.5s ease-in-out infinite;
}

/* Actions */
.action-card {
  background: rgba(var(--card-rgb), 0.38);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 0;
  box-shadow: inset 0 1px 0 0 rgba(255,255,255,0.04);
  border-radius: 8px;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: background 0.3s ease, border-color 0.3s ease;
}
.btn-row { display: flex; gap: 8px; }
.action-heading { font-size:14px; font-weight:600; margin-bottom:6px; }
.action-heading span { display:block; margin-top:5px; font-size:11px; font-weight:400; color:var(--text-secondary); }
.action-card svg { width:18px; height:18px; flex-shrink:0; fill:none; stroke:currentColor; stroke-width:1.5; stroke-linecap:round; stroke-linejoin:round; }
.action-arrow { display:none; }
.btn {
  padding: 10px 16px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s ease;
  text-align: center;
  font-weight: 500;
}
.btn:hover:not(:disabled) {
  background: var(--accent-glow);
  border-color: var(--text-tertiary);
  color: var(--text);
}
.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  font-weight: 600;
}
.btn.primary:hover:not(:disabled) {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
  box-shadow: 0 0 20px var(--accent-glow);
}
.btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.btn-row .btn { flex:1; display:flex; align-items:center; justify-content:center; gap:6px; min-height:44px; padding:10px 6px; font-size:12px; white-space:nowrap; border-radius:6px; }
.btn-row .btn:disabled { opacity:.45; }

/* Cancel */
.cancel-card {
  background: rgba(var(--card-rgb), 0.38);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(var(--text-rgb), 0.09);
  box-shadow: inset 0 1px 0 0 rgba(255,255,255,0.04);
  border-radius: 8px;
  padding: 6px;
  display: flex;
  justify-content: center;
  transition: background 0.3s ease, border-color 0.3s ease;
  margin-top: auto;
}
.cancel-btn {
  flex: 0 1 140px;
  max-width: 140px;
}

/* View toggle */
.view-toggle { margin-top: 0; }
.view-toggle-label {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.view-toggle-btns { display: flex; gap: 6px; }
.view-toggle .btn { flex: 1; padding: 8px; font-size: 12px; }
.btn.active-state {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-glow);
}

@keyframes charge {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}
@keyframes pop {
  0%   { transform: scale(0.8); }
  60%  { transform: scale(1.15); }
  100% { transform: scale(1); }
}
@keyframes check-pop {
  0%   { transform: scale(0.6); }
  60%  { transform: scale(1.1); }
  100% { transform: scale(1); }
}
@keyframes focus-breathe {
  0%, 100% { box-shadow: 0 0 0 3px var(--accent-glow); }
  50%      { box-shadow: 0 0 0 5px var(--accent-glow); }
}
.sidebar { background:radial-gradient(ellipse at top left,var(--accent-glow),transparent 65%),var(--panel); }
.action-card { padding:16px; border:1px solid var(--border); border-radius:12px; background:var(--panel); box-shadow:0 8px 26px #00000005; }
.btn-row { gap:10px; }
.btn-row .btn { position:relative; overflow:hidden; isolation:isolate; min-height:46px; padding:10px 8px; font-size:13px; border-radius:8px; box-shadow:inset 0 1px 0 #ffffff35,0 3px 0 #00000015; transition:transform .18s ease,box-shadow .18s ease,background .18s ease; }
.btn-row .btn::before { content:''; pointer-events:none; position:absolute; inset:0; background:linear-gradient(110deg,transparent 20%,#ffffff30 50%,transparent 80%); transform:translateX(-130%); }
.btn-row .btn:hover:not(:disabled) { color:#fff; transform:translateY(-2px); box-shadow:inset 0 1px 0 #ffffff35,0 6px 18px var(--accent-glow); }
.btn-row .btn:hover:not(:disabled)::before { animation:sweep .65s ease-out; }
.btn-row .btn:active:not(:disabled) { transform:translateY(1px) scale(.98); box-shadow:inset 0 2px 5px #00000025; }
.btn-row svg { transition:transform .2s ease; }
.btn-row .btn:hover:not(:disabled) svg { transform:translateY(-1px) rotate(-5deg); }
.btn-row .btn.processing { opacity:1; box-shadow:0 0 0 3px var(--accent-glow); cursor:progress; }
.btn-row .btn.processing::before { animation:sweep 1.8s ease-in-out infinite; }
.settings-top,.view-toggle .btn { transition:transform .18s ease,background .18s ease,border-color .18s ease; }
.settings-top:hover { background:var(--accent-glow); border-color:var(--accent); }
.settings-top:active,.theme-btn:active,.view-toggle .btn:active { transform:scale(.96); }
.registration-summary { padding:10px 12px; border-left:2px solid var(--accent); background:var(--accent-glow); border-radius:0 8px 8px 0; }
.qty-input:focus,.biz-select:focus { animation:none; }
@keyframes sweep { to { transform:translateX(130%); } }
@media (max-width:800px) { .sidebar { padding:20px; } .action-card { padding:12px; } .btn-row .btn { font-size:12px; } }
@media (max-width:680px) { .sidebar { width:100%; min-width:0; flex-shrink:0; overflow:visible; border-right:0; border-bottom:1px solid var(--border); } }
</style>
