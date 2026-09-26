<script setup lang="ts">
import { reactive, ref, watch, onMounted, nextTick } from 'vue'
import { invoke } from '@tauri-apps/api/core'

const props = defineProps<{ isRunning: boolean }>()
const emit = defineEmits<{ connected: [endpoint: string]; busy: [value: boolean]; settings: [] }>()
const settings = reactive({ mode: 'smart', port: 9222, profile: '', executable: '' })
const loaded = ref(false)
const dirty = ref(false)
const busy = ref(false)
const activeAction = ref('')
const connected = ref(false)
const message = ref('正在读取本机设置…')
const error = ref(false)
const notice = ref(false)
watch(settings, () => {
  if (!loaded.value) return
  dirty.value = true
  emit('busy', true)
  connected.value = false
  emit('connected', '')
  message.value = '浏览器设置有未保存的更改。'
})

onMounted(async () => {
  emit('busy', true)
  try {
    let legacy = null
    try { legacy = JSON.parse(localStorage.getItem('browser-settings') || 'null') } catch { /* Missing legacy preferences use defaults. */ }
    const saved = await invoke<typeof settings>('get_browser_settings', { legacy })
    Object.assign(settings, saved)
    await nextTick()
    loaded.value = true
    message.value = '沿用原快捷方式打开 Chrome，即可连接。'
    emit('busy', false)
  } catch (e) { error.value = true; message.value = `配置读取失败：${e}` }
})

async function save() {
  busy.value = true
  try {
    await invoke('save_browser_settings', { settings: { ...settings } })
    dirty.value = false
    error.value = false
    message.value = '设置已保存，请重新连接。'
  } catch (e) { error.value = true; message.value = String(e) }
  finally { busy.value = false; emit('busy', dirty.value) }
}

async function run(action: 'detect' | 'connect' | 'launch') {
  if (busy.value || props.isRunning || !loaded.value || dirty.value) return
  busy.value = true
  activeAction.value = action
  emit('busy', true)
  connected.value = false
  emit('connected', '')
  error.value = false
  notice.value = action !== 'connect'
  message.value = action === 'launch' ? '正在启动专用浏览器…' : action === 'connect' ? '正在连接；新版 Chrome 如出现提示，请点击允许（最多等待 60 秒）。' : '正在检测，不会打开新窗口或请求授权…'
  try {
    if (!Number.isInteger(settings.port) || settings.port < 1 || settings.port > 65535) throw new Error('端口需填写 1 到 65535 的整数')
    let endpoint: string
    if (action === 'launch') {
      endpoint = await invoke<string>('launch_chrome', { port: settings.port, executable: settings.executable })
    } else {
      const result = await invoke<{ endpoint: string; message: string }>('detect_chrome', { mode: settings.mode, port: settings.port, profile: settings.profile })
      if (action === 'detect') { message.value = result.message; return }
      endpoint = result.endpoint
      await invoke('connect_chrome', { cdpEndpoint: endpoint })
    }
    connected.value = true
    emit('connected', endpoint)
    message.value = action === 'launch' ? '专用浏览器已就绪，请在该窗口登录并打开审批页。' : '连接验证通过，请在该浏览器打开审批页。开始审批时可能再次请求授权。'
  } catch (e) {
    error.value = true
    message.value = String(e)
  } finally {
    busy.value = false
    activeAction.value = ''
    emit('busy', false)
  }
}
</script>

<template>
  <section class="browser-card" :class="{ 'is-busy': busy }" :data-action="activeAction">
    <div class="connection-bar">
    <div class="connection-state" :title="message"><i :class="{ ready: connected }"></i><span>Chrome<small>{{ connected ? '连接已验证' : '未连接' }}</small></span></div>
    <fieldset :disabled="busy || isRunning || !loaded || dirty">
      <div class="actions">
        <button aria-label="连接 Chrome" title="连接已打开的 Chrome；已连接时重新验证" @click="run('connect')"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 15 6-6m-8 4-2 2a4 4 0 0 0 6 6l3-3m-4-12 3-3a4 4 0 0 1 6 6l-2 2"/></svg><span>连接</span></button>
        <button aria-label="检测" title="检测调试状态，不启动浏览器" @click="run('detect')"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3H4a1 1 0 0 0-1 1v3m14-4h3a1 1 0 0 1 1 1v3M3 17v3a1 1 0 0 0 1 1h3m10 0h3a1 1 0 0 0 1-1v-3M7 12l3 3 7-7"/></svg><span>检测</span></button>
        <button aria-label="启动专用浏览器" title="启动专用浏览器，保留登录状态" @click="run('launch')"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="3" width="20" height="18" rx="3"/><path d="M2 8h20M6 5.5h.1m3 0h.1"/><path d="m10 11 6 3.5-6 3.5Z" fill="currentColor" stroke="none"/></svg><span>专用浏览器</span></button>
      </div>
    </fieldset>
    </div>
    <p v-if="busy || error || dirty || notice" class="message" :class="{ error }" role="status" aria-live="polite">{{ message }}</p>
    <button v-if="dirty || error" class="settings-link" @click="emit('settings')">查看连接设置</button>
    <Teleport defer to="#browser-settings-pane">
    <div class="browser-preferences">
    <h3>浏览器连接</h3>
    <p class="hint">推荐自动识别，优先连接原有 9222 调试浏览器。不会自动启动新窗口。</p>
    <fieldset :disabled="busy || isRunning || !loaded">
      <label for="browser-mode">连接方式</label>
      <select id="browser-mode" v-model="settings.mode">
        <option value="smart">自动识别（推荐）</option>
        <option value="auto">新版 Chrome 授权连接</option>
        <option value="port">手动调试端口连接</option>
      </select>
      <p v-if="settings.mode === 'auto'" class="hint">Chrome 144+：先在 <code>chrome://inspect/#remote-debugging</code> 启用。允许连接意味着程序可访问此浏览器的页面。</p>
      <p v-else class="hint">支持 localhost、IPv4 和 IPv6。原有 ChromeDebug 快捷方式无需修改。</p>
      <details>
        <summary>高级连接参数</summary>
        <label for="browser-port">手动连接 / 专用浏览器端口</label>
        <input id="browser-port" v-model.number="settings.port" type="number" min="1" max="65535" />
        <label for="browser-exe">Chrome 程序路径（可选）</label>
        <input id="browser-exe" v-model="settings.executable" placeholder="留空自动查找 chrome.exe" />
        <label for="browser-profile">新版 Chrome 资料根目录（可选）</label>
        <input id="browser-profile" v-model="settings.profile" placeholder="留空使用默认 User Data 目录" />
        <p class="hint">专用浏览器使用独立资料目录，关闭后保留登录资料；更换端口将使用另一份专用资料。</p>
      </details>
      <button class="primary" :disabled="!dirty" @click="save">保存浏览器设置</button>
    </fieldset>
    <p class="message" :class="{ error }" role="status">{{ message }}</p>
    </div>
    </Teleport>
  </section>
</template>

<style scoped>
.browser-card { padding: 10px 0; border-bottom: 1px solid var(--border); }
.connection-bar { display:flex; flex-direction:column; align-items:stretch; gap:8px; }
.connection-bar fieldset { flex-shrink:0; }
.actions button { flex:1; height:34px; white-space:nowrap; display:flex; align-items:center; justify-content:center; gap:5px; padding:6px; }
.actions button:last-child { flex:1.7; }
.actions svg { width:17px; height:17px; flex-shrink:0; fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; }
.connection-state { display:flex; align-items:center; gap:8px; font-size:12px; }
.connection-state span { display:flex; align-items:center; justify-content:space-between; flex:1; }
.connection-state small { font-size:10px; color:var(--text-secondary); }
.connection-state i { width:6px; height:6px; border-radius:50%; background:var(--text-tertiary); }
.connection-state i.ready { background:var(--success); }
.icon-button svg { width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; }
button.icon-button { display:grid; place-items:center; width:30px; padding:6px; }
button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.heading { display:flex; justify-content:space-between; font-size:13px; font-weight:600; margin-bottom:12px; }
.heading span { color:var(--text-secondary); font-size:11px; font-weight:400; }
.heading .ready { color:var(--success); }
fieldset { border:0; padding:0; margin:0; min-width:0; }
label { display:block; font-size:11px; color:var(--text-secondary); margin:10px 0 5px; }
select, input { box-sizing:border-box; width:100%; padding:7px; border:1px solid var(--border); border-radius:5px; background:var(--bg); color:var(--text); font:inherit; font-size:12px; }
.hint { font-size:11px; color:var(--text-secondary); line-height:1.6; margin:7px 0; overflow-wrap:anywhere; }
code { font-size:10px; user-select:all; }
.actions { display:flex; gap:5px; }
button { flex:1; padding:8px; border:1px solid var(--border); border-radius:5px; color:var(--text); background:transparent; cursor:pointer; font:inherit; font-size:12px; }
button:hover { border-color:var(--accent); }
button.primary { background:var(--accent); color:white; border-color:var(--accent); }
fieldset:disabled { opacity:.55; }
fieldset:disabled button { cursor:wait; }
summary { cursor:pointer; color:var(--text-secondary); font-size:11px; padding:7px 0; }
.dedicated { border-top:1px solid var(--border); padding-top:12px; margin-top:8px; }
.dedicated button { width:100%; }
.message { font-size:12px; line-height:1.6; margin:10px 0 0; overflow-wrap:anywhere; color:var(--text-secondary); }
.message.error { color:var(--error, #b4533c); }
.secondary { width:100%; }
.settings-link { border:0; color:var(--accent); padding:8px 0 0; }
.browser-preferences h3 { font-size:17px; margin-bottom:8px; }
.browser-preferences label { font-size:13px; margin-top:16px; }
.browser-preferences input, .browser-preferences select { font-size:13px; padding:10px; }
.browser-preferences .hint { font-size:12px; }
.actions button { position:relative; transition:background .18s ease,transform .18s ease,box-shadow .18s ease; }
.actions button:hover:not(:disabled) { background:var(--accent-glow); box-shadow:0 2px 8px #00000008; transform:translateY(-1px); }
.actions button:active:not(:disabled) { transform:translateY(1px) scale(.97); }
.actions svg { transition:transform .2s ease; }
.actions button:hover:not(:disabled) svg { transform:scale(1.12); }
.is-busy[data-action="connect"] .actions button:nth-child(1),
.is-busy[data-action="detect"] .actions button:nth-child(2),
.is-busy[data-action="launch"] .actions button:nth-child(3) { color:var(--accent); border-color:var(--accent); background:var(--accent-glow); }
.is-busy .connection-state i { animation:connection-pulse 1s ease-in-out infinite; background:var(--accent); }
@keyframes connection-pulse { 50% { box-shadow:0 0 0 4px var(--accent-glow); } }
</style>
