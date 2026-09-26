<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import WechatSettings from './WechatSettings.vue'

defineProps<{ isRunning: boolean }>()
const emit = defineEmits<{ busy: [value: boolean]; summary: [value: string] }>()
const configPath = 'src-tauri/python/config.json'
const settings = ref({ wechat_enabled: true, obsidian_enabled: false, obsidian_directory: '',
  wechat_url: '', wechat_schema: {} as Record<string, string>, wechat_timeout: 10 })
const loaded = ref(false)
const busy = ref(false)
const dirty = ref(false)
const message = ref('正在读取登记设置…')
const error = ref(false)
const expanded = ref(true)

function publishSummary() {
  emit('summary', `企业微信 ${settings.value.wechat_enabled ? '已启用' : '未启用'} · Obsidian ${settings.value.obsidian_enabled ? '已启用' : '未启用'}`)
}

function changed() {
  dirty.value = true
  message.value = '有未保存的更改，保存后再开始审批'
  error.value = false
  emit('busy', true)
}

onMounted(async () => {
  emit('busy', true)
  try {
    settings.value = await invoke('get_push_settings', { configPath })
    loaded.value = true
    publishSummary()
    message.value = ''
    emit('busy', false)
  } catch (e) {
    message.value = `读取失败：${e}`
    error.value = true
  }
})

async function chooseDirectory() {
  busy.value = true
  emit('busy', true)
  try {
    const directory = await invoke<string | null>('select_obsidian_directory')
    if (directory) {
      settings.value.obsidian_directory = directory
      changed()
    }
  } catch (e) {
    message.value = `选择失败：${e}`
    error.value = true
  } finally {
    busy.value = false
    emit('busy', dirty.value)
  }
}

async function save() {
  busy.value = true
  emit('busy', true)
  try {
    await invoke('save_push_settings', { configPath, settings: settings.value })
    dirty.value = false
    publishSummary()
    error.value = false
    message.value = '已保存，下次审批生效'
  } catch (e) {
    message.value = `保存失败：${e}`
    error.value = true
  } finally {
    busy.value = false
    emit('busy', dirty.value)
  }
}
</script>

<template>
  <section class="push-settings" aria-label="数据登记设置">
    <button class="settings-summary" type="button" :aria-expanded="expanded" aria-controls="push-settings-body" @click="expanded = !expanded">
      <span><strong>数据登记</strong><span class="summary-status">企业微信 {{ settings.wechat_enabled ? '开' : '关' }} · Obsidian {{ settings.obsidian_enabled ? '开' : '关' }}</span></span>
      <span class="expand-label">{{ expanded ? '收起' : '设置' }} <span aria-hidden="true">{{ expanded ? '−' : '+' }}</span></span>
    </button>
    <div v-show="expanded" id="push-settings-body" class="settings-body">
    <div class="heading">登记通道</div>
    <fieldset :disabled="isRunning || busy || !loaded">
      <label class="toggle-row">
        <span>企业微信推送</span>
        <input v-model="settings.wechat_enabled" type="checkbox" role="switch" @change="changed" />
      </label>
      <WechatSettings v-model="settings" :disabled="isRunning || busy || !loaded"
        :dirty="dirty" :message="message" :error="error" @change="changed" @save="save" />
      <label class="toggle-row">
        <span>Obsidian 本地登记</span>
        <input v-model="settings.obsidian_enabled" type="checkbox" role="switch" @change="changed" />
      </label>
      <div v-if="settings.obsidian_enabled" class="directory">
        <label for="obsidian-directory">记录文件夹</label>
        <input id="obsidian-directory" v-model="settings.obsidian_directory" type="text"
          placeholder="选择本机 Obsidian 库中的文件夹" @input="changed" />
        <button type="button" @click="chooseDirectory">选择目录…</button>
        <p>每条审批保存为 Markdown 记录；Base 读取记录属性，无需选择 .base 文件。</p>
      </div>
      <p v-if="!settings.wechat_enabled && !settings.obsidian_enabled">当前仅审批与提取，不登记数据。</p>
      <button type="button" class="save" :disabled="!dirty" @click="save">{{ busy ? '处理中…' : '保存设置' }}</button>
    </fieldset>
    </div>
    <p v-if="message" role="status" :class="{ error }">{{ message }}</p>
  </section>
</template>

<style scoped>
.push-settings { --border: rgba(var(--text-rgb), .12); padding: 14px; border: 1px solid var(--border); border-radius: 8px; background: rgba(var(--card-rgb), .38); color: var(--text); }
.heading { font-size: 12px; font-weight: 600; display: flex; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.settings-summary { display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 0; border: 0; background: transparent; text-align: left; gap: 10px; }
.settings-summary strong { font-size: 13px; }
.summary-status { display: block; color: var(--text-secondary); font-size: 11px; margin-top: 4px; font-weight: 400; }
.expand-label { flex-shrink: 0; color: var(--accent); font-size: 12px; }
.settings-body { padding-top: 16px; margin-top: 14px; border-top: 1px solid var(--border); }
.heading span, p { color: var(--text-tertiary); font-size: 11px; line-height: 1.6; }
fieldset { margin: 0; padding: 0; border: 0; min-width: 0; display: grid; gap: 12px; }
.toggle-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; cursor: pointer; }
input[type=checkbox] { appearance: none; width: 30px; height: 18px; border-radius: 10px; background: var(--border); position: relative; cursor: pointer; flex-shrink: 0; }
input[type=checkbox]::after { content: ''; position: absolute; width: 12px; height: 12px; left: 3px; top: 3px; border-radius: 50%; background: var(--text-secondary); transition: transform .15s; }
input[type=checkbox]:checked { background: #14b8a6; }
input[type=checkbox]:checked::after { transform: translateX(12px); background: white; }
.directory { display: grid; gap: 8px; font-size: 12px; }
input[type=text] { box-sizing: border-box; width: 100%; min-width: 0; padding: 8px; background: var(--panel); color: var(--text); border: 1px solid var(--border); border-radius: 5px; font: inherit; }
button { padding: 8px; border-radius: 5px; background: var(--panel); color: var(--text); border: 1px solid var(--border); font: inherit; font-size: 12px; cursor: pointer; }
button:hover:not(:disabled) { border-color: var(--accent); }
:disabled { opacity: .5; cursor: not-allowed; }
.save { color: var(--accent); background: var(--accent-glow); font-weight: 600; }
p { margin: 0; }
.push-settings > p { margin-top: 8px; }
.error { color: var(--error, #e65b5b); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
</style>
