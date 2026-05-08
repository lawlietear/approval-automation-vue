<script setup lang="ts">
import { ref, computed } from 'vue'
import { useMagnetic } from '../composables/useMagnetic'

const props = defineProps<{
  isDark: boolean
  isConnected: boolean
  stepIndex: number
  hasExtractedData: boolean
  countdown: number
  isRunning: boolean
  view: 'empty' | 'loading' | 'data'
  bizTypeOptions: string[]
}>()

const emit = defineEmits<{
  toggleTheme: []
  connect: []
  start: [payload: { system: 'core' | 'oa'; qty: string; bizType: string }]
  cancel: []
  switchView: [view: 'empty' | 'data']
}>()

const qty = ref('1')
const bizType = ref('金融不良资产')

const sysDisabled = computed(() => !props.isConnected || props.isRunning)

const handleSystem = (system: 'core' | 'oa') => {
  if (sysDisabled.value) return
  emit('start', { system, qty: qty.value, bizType: bizType.value })
}

const btnCoreRef = ref<HTMLElement | null>(null)
const btnOaRef = ref<HTMLElement | null>(null)

const coreOffset = useMagnetic(btnCoreRef, 6, 80)
const oaOffset = useMagnetic(btnOaRef, 6, 80)
</script>

<template>
  <div class="sidebar">
    <div class="logo">
      <div>自动化审批 <span>v2.0.0</span></div>
      <button class="theme-btn" @click="emit('toggleTheme')" title="切换主题">
        <span>{{ isDark ? '☼' : '☾' }}</span>
      </button>
    </div>

    <div class="steps">
      <div class="step" :class="{ completed: stepIndex > 0, active: stepIndex === 0 }">
        <div class="step-icon">{{ stepIndex > 0 ? '✓' : '1' }}</div>
        <div class="step-label">conn</div>
      </div>
      <div class="step-line" :class="{ completed: stepIndex >= 1 }"></div>
      <div class="step" :class="{ completed: stepIndex > 1, active: stepIndex === 1 }">
        <div class="step-icon">{{ stepIndex > 1 ? '✓' : '2' }}</div>
        <div class="step-label">pull</div>
      </div>
      <div class="step-line" :class="{ completed: stepIndex >= 2 }"></div>
      <div class="step" :class="{ completed: stepIndex > 2, active: stepIndex === 2 }">
        <div class="step-icon">{{ stepIndex > 2 ? '✓' : '3' }}</div>
        <div class="step-label">submit</div>
      </div>
      <div class="step-line" :class="{ completed: stepIndex >= 3 }"></div>
      <div class="step" :class="{ completed: stepIndex > 3, active: stepIndex === 3 }">
        <div class="step-icon">{{ stepIndex > 3 ? '✓' : '4' }}</div>
        <div class="step-label">done</div>
      </div>
    </div>

    <div class="status-card">
      <div class="status-header">
        <div class="status-dot" :class="{ pulse: isConnected }"></div>
        <div class="status-label">chrome status</div>
      </div>
      <div class="status-title" :class="{ connected: isConnected }">
        {{ isConnected ? 'connected' : 'disconnected' }}
      </div>
      <div class="status-sub">
        {{ isConnected ? '核心业务管理系统' : 'connect to begin' }}
      </div>
      <button
        class="status-connect-btn"
        :disabled="isRunning"
        @click="emit('connect')"
      >{{ isConnected ? '重新连接' : '连接 Chrome' }}</button>
    </div>

    <div class="param-card">
      <div class="param-section">
        <div class="param-label">数量</div>
        <div class="qty-row">
          <button
            v-for="n in ['1','2','3','4','5']"
            :key="n"
            class="qty-btn"
            :class="{ active: qty === n }"
            @click="qty = n"
          >{{ { '1': 'I', '2': 'II', '3': 'III', '4': 'IV', '5': 'V' }[n] }}</button>
          <span class="custom-label">其他:</span>
          <input type="text" class="qty-input" placeholder="数量" v-model="qty" />
        </div>
      </div>
      <div class="param-section">
        <div class="param-label">业务类型</div>
        <select class="biz-select" v-model="bizType">
          <option v-for="opt in bizTypeOptions" :key="opt">{{ opt }}</option>
        </select>
      </div>
    </div>

    <div class="action-card">
      <div class="btn-row">
        <button
          ref="btnCoreRef"
          class="btn primary"
          :disabled="sysDisabled"
          @click="handleSystem('core')"
          :style="{ transform: `translate(${coreOffset.x}px, ${coreOffset.y}px)` }"
        >核心业务系统</button>
        <button
          ref="btnOaRef"
          class="btn primary"
          :disabled="sysDisabled"
          @click="handleSystem('oa')"
          :style="{ transform: `translate(${oaOffset.x}px, ${oaOffset.y}px)` }"
        >OA 系统</button>
      </div>
    </div>

    <div class="view-toggle" v-show="hasExtractedData">
      <div class="view-toggle-label">view</div>
      <div class="view-toggle-btns">
        <button
          class="btn"
          :class="{ 'active-state': view === 'data' }"
          @click="emit('switchView', 'data')"
        >detail</button>
        <button
          class="btn"
          :class="{ 'active-state': view === 'empty' }"
          @click="emit('switchView', 'empty')"
        >empty</button>
      </div>
    </div>

    <div class="countdown" :class="{ show: countdown > 0 }">
      auto-hide in {{ countdown }}s...
    </div>

    <div class="cancel-card">
      <button
        class="btn cancel-btn"
        :disabled="!isRunning"
        @click="emit('cancel')"
      >取消</button>
    </div>
  </div>
</template>

<style scoped>
.sidebar {
  width: 320px;
  background: var(--panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 24px;
  gap: 16px;
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
  padding: 14px;
  background: rgba(var(--card-rgb), 0.38);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(var(--text-rgb), 0.09);
  box-shadow: inset 0 1px 0 0 rgba(255,255,255,0.04);
  border-radius: 8px;
  transition: background 0.3s ease, border-color 0.3s ease;
}
.step {
  display: flex;
  flex-direction: column;
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
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
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
  font-family: 'Times New Roman', 'Georgia', serif;
  cursor: pointer;
  transition: all 0.2s;
}
.qty-btn:hover { border-color: var(--accent); color: var(--accent); }
.qty-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.custom-label { font-size: 12px; color: var(--text-secondary); margin-left: 4px; }
.qty-input {
  width: 60px;
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
  border: 1px solid rgba(var(--text-rgb), 0.09);
  box-shadow: inset 0 1px 0 0 rgba(255,255,255,0.04);
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: background 0.3s ease, border-color 0.3s ease;
}
.btn-row { display: flex; gap: 8px; }
.btn {
  padding: 10px 16px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
  font-family: 'Inter', sans-serif;
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
.btn-row .btn { flex: 1; padding: 10px 8px; font-size: 12px; }

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

/* Countdown */
.countdown {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 0;
  text-align: center;
  opacity: 0;
  transition: opacity 0.3s;
  font-family: 'JetBrains Mono', monospace;
}
.countdown.show { opacity: 1; }

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
</style>
