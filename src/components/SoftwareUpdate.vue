<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
defineProps<{ disabled: boolean }>()
const emit = defineEmits<{ busy: [value: boolean] }>()
const info = ref({ version: '', configured: false, last_result: null as null | { ok: boolean; message: string } })
const update = ref<null | { available: boolean; version?: string; notes?: string }>(null)
const busy = ref(false)
const installing = ref(false)
const confirm = ref(false)
const message = ref('正在读取版本信息…')
const error = ref(false)
const percent = ref<number | null>(null)
let unlisten: UnlistenFn | undefined
onMounted(async () => {
  try {
    info.value = await invoke('update_info')
    message.value = info.value.configured ? '按需检查，不在审批过程中自动更新。' : '更新服务尚未配置。发布者接通下载源后即可使用，不影响当前功能。'
    unlisten = await listen<{ downloaded: number; total?: number }>('update:progress', ({ payload }) => {
      percent.value = payload.total ? Math.min(100, Math.floor(payload.downloaded / payload.total * 100)) : null
      message.value = `正在下载 ${(payload.downloaded / 1048576).toFixed(1)} MB，下载后校验签名…`
    })
  } catch (e) { message.value = String(e); error.value = true }
})
onUnmounted(() => unlisten?.())
async function check() {
  busy.value = true
  emit('busy', true)
  error.value = false
  update.value = null
  confirm.value = false
  message.value = '正在检查新版…'
  try {
    update.value = await invoke('check_update')
    message.value = update.value?.available ? `发现新版本 ${update.value.version}` : '当前已是最新版。'
  } catch (e) { error.value = true; message.value = String(e) }
  finally { busy.value = false; emit('busy', false) }
}
async function install() {
  busy.value = true
  installing.value = true
  emit('busy', true)
  error.value = false
  try {
    await invoke('install_update')
    message.value = '校验通过，正在退出并更新程序…'
  } catch (e) {
    error.value = true
    message.value = String(e)
    busy.value = false
    installing.value = false
    emit('busy', false)
  }
}
</script>

<template>
  <section class="software-update">
    <span class="edition">绿色免安装版</span>
    <h3>软件更新 <span>v{{ info.version }}</span></h3>
    <p>只更新软件和运行组件，不覆盖企业微信、Obsidian、浏览器设置，也不清除 Chrome 登录资料。</p>
    <p v-if="info.last_result" :class="{ error: !info.last_result.ok }">上次更新：{{ info.last_result.ok ? info.last_result.message : '未完成，原因：' + info.last_result.message }}</p>
    <button :disabled="disabled || busy || !info.configured" @click="check">{{ busy && !installing ? '正在检查…' : '检查更新' }}</button>
    <p role="status" :class="{ error }">{{ message }}</p>
    <div v-if="update?.available" class="release">
      <h4>新版说明</h4><p class="notes">{{ update.notes || '发布者未填写更新说明。' }}</p>
      <label><input v-model="confirm" type="checkbox" :disabled="busy" /> 我已完成当前工作，允许更新后重启审批工具</label>
      <button class="primary" :disabled="!confirm || disabled || busy" @click="install">{{ installing ? '正在更新…' : '下载并更新' }}</button>
      <progress v-if="installing" :value="percent ?? undefined" max="100"></progress>
    </div>
    <small>无需安装器。请将程序保存在有写入权限的文件夹；下载失败或签名不匹配不会替换现有程序。</small>
  </section>
</template>

<style scoped>
.edition { color:var(--accent); font-size:11px; }
h3 { font-size:19px; margin:8px 0 16px; }
h3 span { color:var(--text-secondary); font-size:13px; font-weight:400; }
p { color:var(--text-secondary); font-size:13px; line-height:1.8; margin:12px 0; }
button { padding:10px 18px; border:1px solid var(--border); border-radius:6px; background:var(--panel); color:var(--text); cursor:pointer; font:inherit; font-size:13px; }
button:disabled { opacity:.5; cursor:not-allowed; }
button.primary { background:var(--accent); color:white; margin-top:14px; }
.release { padding:18px; background:var(--accent-glow); border:1px solid var(--border); border-radius:8px; margin:16px 0; }
.notes { white-space:pre-wrap; overflow-wrap:anywhere; }
label { display:block; font-size:12px; line-height:1.8; }
small { display:block; font-size:11px; color:var(--text-tertiary); line-height:1.7; margin-top:20px; }
.error { color:var(--error); }
progress { display:block; width:100%; margin-top:12px; accent-color:var(--accent); }
</style>
