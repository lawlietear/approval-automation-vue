<script setup lang="ts">
import { ref, watch } from 'vue'

interface WechatConfig {
  wechat_enabled: boolean
  obsidian_enabled: boolean
  obsidian_directory: string
  wechat_url: string
  wechat_schema: Record<string, string>
  wechat_timeout: number
}
const settings = defineModel<WechatConfig>({ required: true })
const props = defineProps<{ disabled: boolean; dirty: boolean; message: string; error: boolean }>()
const emit = defineEmits<{ change: []; save: [] }>()
const dialog = ref<HTMLDialogElement>()
const showUrl = ref(false)
const example = ref('')
const importMessage = ref('')
const fields = [
  ['title', '项目名称', '事项名称'], ['time', '时间', '登记时间'],
  ['dept', '部门', '部门'], ['biz_type', '业务类型', '业务类型'],
  ['work_type', '工作类型', '工作类型'], ['qty', '数量', '数量'],
  ['remark', '备注', '备注'], ['counterparty', '交易对手', '交易对手'],
  ['contract_amount', '合同金额', '合同金额'], ['contract_name', '合同名称', '合同名称'],
  ['contract_no', '合同编号', '合同编号'],
] as const

watch(() => props.dirty, (dirty, previous) => {
  if (previous && !dirty && !props.error) dialog.value?.close()
})

function importFields() {
  try {
    const value = JSON.parse(example.value)
    const schema = value.webhook?.schema ?? value.schema ?? value
    if (!schema || Array.isArray(schema) || typeof schema !== 'object') throw new Error()
    const result: Record<string, string> = {}
    for (const [key, label, source] of fields) {
      if (typeof schema[key] === 'string' && schema[key].trim()) {
        result[key] = schema[key].trim()
      } else {
        const match = Object.entries(schema).find(([, name]) => name === label || name === source)
        if (match) result[key] = match[0]
      }
    }
    if (!Object.keys(result).length) {
      importMessage.value = '未识别到对应字段。请检查示例中的字段名称，或在下方手动填写。'
      return
    }
    settings.value = { ...settings.value, wechat_schema: result }
    emit('change')
    example.value = ''
    importMessage.value = `已填入 ${Object.keys(result).length} 个字段，请核对后保存。未识别的字段留空。`
  } catch {
    importMessage.value = '示例格式无法识别，请粘贴完整的 JSON 请求示例（包含 schema）。'
  }
}
</script>

<template>
  <button type="button" class="configure" :disabled="disabled" @click="dialog?.showModal()">配置企业微信链接与字段</button>
  <Teleport to="body">
    <dialog ref="dialog" class="wechat-dialog" aria-labelledby="wechat-heading">
      <header>
        <div><span class="eyebrow">数据登记 / 企业微信</span><h2 id="wechat-heading">连接你的智能表格</h2></div>
        <button type="button" aria-label="关闭企业微信设置" @click="dialog?.close()">关闭</button>
      </header>
      <div class="dialog-content">
        <p class="intro">粘贴目标智能表格的 Webhook 链接，设置审批信息写入哪些列。保存后即可使用，无需编辑配置文件。</p>
        <fieldset :disabled="disabled">
          <section>
            <h3>1. 接收数据的链接</h3>
            <label for="wechat-url">企业微信智能表格 Webhook 链接</label>
            <div class="url-row">
              <input id="wechat-url" v-model="settings.wechat_url" :type="showUrl ? 'text' : 'password'"
                autocomplete="off" spellcheck="false" placeholder="https://qyapi.weixin.qq.com/cgi-bin/wedoc/smartsheet/webhook?key=…" @input="emit('change')" />
              <button type="button" @click="showUrl = !showUrl">{{ showUrl ? '隐藏' : '显示' }}</button>
            </div>
            <p class="hint">使用智能表格的 Webhook 地址；普通表格分享链接、群机器人地址不适用。链接包含写入凭据，请勿公开分享。</p>
          </section>
          <section>
            <h3>2. 对应表格中的列</h3>
            <p class="hint">不同表格的字段标识不同。项目名称必填；不需要登记的字段留空。左侧为审批信息，右侧填目标表格字段标识。</p>
            <details class="import-box">
              <summary>从 Webhook 请求示例自动填入（推荐）</summary>
              <p class="hint">粘贴含 schema 的 JSON 示例，程序会按字段名称匹配。也兼容旧配置的 webhook.schema；不会修改链接。</p>
              <textarea v-model="example" aria-label="Webhook 请求示例" rows="4" spellcheck="false" placeholder='例如：{"schema":{"字段标识":"项目名称"}}'></textarea>
              <button type="button" @click="importFields">识别并填入字段</button>
              <p role="status" class="hint">{{ importMessage }}</p>
            </details>
            <div class="mapping-grid">
              <label v-for="[key, label] in fields" :key="key" :for="`wechat-field-${key}`">
                <span>{{ label }}{{ key === 'title' ? ' *' : '' }}</span>
                <input :id="`wechat-field-${key}`" v-model="settings.wechat_schema[key]" type="text"
                  :aria-label="`${label}字段标识`" :placeholder="key === 'title' ? '必填：目标列的字段标识' : '留空则不登记此列'" @input="emit('change')" />
              </label>
            </div>
          </section>
          <label class="timeout" for="wechat-timeout">等待响应时间（秒）
            <input id="wechat-timeout" v-model.number="settings.wechat_timeout" type="number" min="1" max="120" @input="emit('change')" />
          </label>
        </fieldset>
      </div>
      <footer>
        <p role="status" :class="{ error }">{{ message || '保存只更新本机配置，不发送测试数据。' }}</p>
        <button type="button" class="save" :disabled="disabled || !dirty" @click="emit('save')">保存设置</button>
      </footer>
    </dialog>
  </Teleport>
</template>

<style scoped>
button, input, textarea { font: inherit; }
button { cursor: pointer; border: 1px solid var(--border); border-radius: 6px; background: var(--panel); color: var(--text); padding: 8px 12px; font-size: 12px; }
.configure { width: 100%; text-align: left; color: var(--accent); background: var(--accent-glow); }
button:disabled, fieldset:disabled { opacity: .5; cursor: not-allowed; }
.wechat-dialog { margin: auto; padding: 0; width: min(720px, calc(100vw - 32px)); max-height: calc(100vh - 32px); border: 1px solid var(--border); border-radius: 14px; color: var(--text); background: var(--panel); box-shadow: 0 24px 80px #0005; }
.wechat-dialog[open] { display: flex; flex-direction: column; }
.wechat-dialog::backdrop { background: #15130f99; }
header, footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 24px; flex-shrink: 0; }
header { border-bottom: 1px solid var(--border); }
.eyebrow { font-size: 11px; color: var(--accent); letter-spacing: .08em; }
h2 { font-size: 20px; margin: 4px 0 0; }
h3 { font-size: 14px; margin-bottom: 10px; }
.dialog-content { overflow-y: auto; padding: 20px 24px; }
.intro { color: var(--text-secondary); font-size: 13px; margin-bottom: 20px; }
fieldset { border: 0; padding: 0; min-width: 0; display: grid; gap: 22px; }
label { display: block; font-size: 12px; }
.hint { color: var(--text-secondary); font-size: 12px; margin-top: 8px; line-height: 1.7; }
input, textarea { width: 100%; border: 1px solid var(--border); padding: 9px 10px; border-radius: 6px; background: var(--bg); color: var(--text); min-width: 0; box-sizing: border-box; font-size: 12px; }
.url-row { display: flex; gap: 8px; margin-top: 8px; }
.url-row button { flex-shrink: 0; }
.mapping-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 16px; margin-top: 16px; }
.mapping-grid span { display: block; margin-bottom: 6px; }
.import-box { margin-top: 12px; padding: 12px; border: 1px solid var(--border); border-radius: 8px; }
summary { cursor: pointer; color: var(--accent); font-size: 12px; }
textarea { resize: vertical; margin: 8px 0; }
.timeout { display: flex; align-items: center; gap: 12px; }
.timeout input { width: 85px; }
footer { border-top: 1px solid var(--border); }
footer p { color: var(--text-secondary); font-size: 12px; }
footer .error { color: var(--error); }
.save { background: var(--accent); color: white; flex-shrink: 0; }
@media (max-width: 520px) { .mapping-grid { grid-template-columns: 1fr; } header, footer, .dialog-content { padding: 16px; } }
</style>
