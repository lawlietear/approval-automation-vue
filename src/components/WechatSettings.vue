<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { analyzeWechatSchema, fieldTypeError, typeNames, wechatFields as fields, type WechatColumn, type SchemaAnalysis } from '../wechatSchema'

interface WechatConfig {
  wechat_enabled: boolean
  obsidian_enabled: boolean
  obsidian_directory: string
  wechat_url: string
  wechat_schema: Record<string, string>
  wechat_timeout: number
  wechat_columns?: Record<string, WechatColumn>
  wechat_value_mappings?: Record<string, Record<string, string>>
}
const settings = defineModel<WechatConfig>({ required: true })
const props = defineProps<{ disabled: boolean; dirty: boolean; message: string; error: boolean }>()
const emit = defineEmits<{ change: []; save: [] }>()
const dialog = ref<HTMLDialogElement>()
const showUrl = ref(false)
const example = ref('')
const importMessage = ref('')
const pending = ref<SchemaAnalysis | null>(null)
const columns = computed(() => settings.value.wechat_columns || {})
const ruleDraft = ref(Object.fromEntries(fields.map(([key]) => [key, { from: '', to: '' }])))
function mappingErrors(mapping: Record<string, string>, catalog: Record<string, WechatColumn>) {
  const errors: string[] = []
  const ids = Object.values(mapping).filter(Boolean)
  if (new Set(ids).size !== ids.length) errors.push('不同审批信息不能写入同一列。')
  for (const [key, label] of fields) {
    const id = mapping[key]
    if (!id) continue
    if (Object.keys(catalog).length && !Object.hasOwn(catalog, id)) errors.push(`${label}：字段不在已导入的列中，请重新选择。`)
    const issue = fieldTypeError(key, catalog[id])
    if (issue) errors.push(`${label}：${issue}`)
  }
  return errors
}
const pendingErrors = computed(() => pending.value ? mappingErrors(pending.value.mapping, pending.value.columns) : [])
const errors = computed(() => mappingErrors(settings.value.wechat_schema, columns.value))
function needsAttention(key: string, mapping = settings.value.wechat_schema, catalog = columns.value) {
  const id = mapping[key]
  return !id || (!!Object.keys(catalog).length && !catalog[id]) || !!fieldTypeError(key, catalog[id])
}
const matchedCount = computed(() => fields.filter(([key]) => !needsAttention(key)).length)
const pendingMatchedCount = computed(() => pending.value ? fields.filter(([key]) => !needsAttention(key, pending.value!.mapping, pending.value!.columns)).length : 0)
const saveBlocked = computed(() => !!pending.value || (settings.value.wechat_enabled && (errors.value.length > 0 || !settings.value.wechat_schema.title)))
function columnLabel(id: string, catalog = columns.value) {
  const col = catalog[id]
  if (!col) return id ? `已配置字段 ${id}（请导入列名）` : '不登记'
  const duplicate = Object.values(catalog).filter(c => c.title === col.title).length > 1
  return `${col.title} · ${typeNames[col.type] || col.type || '类型未提供'}${duplicate ? ` · ${id}` : ''}`
}
function changeKind(key: string) {
  const oldId = settings.value.wechat_schema[key] || ''
  const newId = pending.value?.mapping[key] || ''
  if (!oldId && newId) return '新增'
  if (oldId && !newId) return '将清空'
  if (oldId !== newId) return '变更'
  if (newId && JSON.stringify(columns.value[newId]) !== JSON.stringify(pending.value?.columns[newId])) return '更新列信息'
  return '不变'
}
function fieldChanged(key: string) {
  const rules = { ...settings.value.wechat_value_mappings }
  delete rules[key]
  settings.value.wechat_value_mappings = rules
  emit('change')
}
function choices(key: string) { return columns.value[settings.value.wechat_schema[key] || '']?.enum }
function addRule(key: string) {
  const draft = ruleDraft.value[key]!
  const source = draft.from.trim()
  if (!source || source === draft.to || !choices(key)?.includes(draft.to)) return
  settings.value.wechat_value_mappings = { ...settings.value.wechat_value_mappings,
    [key]: { ...settings.value.wechat_value_mappings?.[key], [source]: draft.to } }
  draft.from = ''; draft.to = ''
  emit('change')
}
function removeRule(key: string, source: string) {
  const rules = { ...settings.value.wechat_value_mappings?.[key] }
  delete rules[source]
  settings.value.wechat_value_mappings = { ...settings.value.wechat_value_mappings, [key]: rules }
  emit('change')
}

watch(() => props.dirty, (dirty, previous) => {
  if (previous && !dirty && !props.error) dialog.value?.close()
})

function importFields() {
  try {
    pending.value = analyzeWechatSchema(example.value)
    importMessage.value = '仅生成预览，原设置未修改。请核对目标列，再确认应用。'
  } catch (e) {
    pending.value = null
    importMessage.value = e instanceof Error ? e.message : '识别失败，原字段未修改。'
  }
}
function applyImport() {
  if (!pending.value || pendingErrors.value.length) return
  settings.value = { ...settings.value, wechat_schema: { ...pending.value.mapping },
    wechat_columns: pending.value.columns, wechat_value_mappings: {} }
  pending.value = null
  example.value = ''
  importMessage.value = '已应用到待保存设置。请核对后保存；未发送任何记录。'
  emit('change')
}
</script>

<template>
  <button type="button" class="configure" :disabled="disabled" @click="dialog?.showModal()">配置企业微信链接与字段</button>
  <Teleport to="body">
    <dialog ref="dialog" class="wechat-dialog" aria-labelledby="wechat-heading" @close="pending = null">
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
            <p class="hint">同名列和常见别名自动对应，无需逐项配置。仅未匹配、有歧义或需要改用其他列时手动调整；项目名称必填，其他信息可不登记。</p>
            <details class="import-box">
              <summary>从 Webhook 请求示例自动填入（推荐）</summary>
              <p class="hint">粘贴完整请求示例（含 title、type、enum）或单独的 schema。先预览，再确认替换；不会发送示例记录或修改链接。</p>
              <textarea v-model="example" aria-label="Webhook 请求示例" rows="4" spellcheck="false" @input="pending = null" placeholder='例如：{"schema":{"字段标识":{"title":"项目名称","type":"text"}}}'></textarea>
              <button type="button" @click="importFields">识别并预览</button>
              <p role="status" class="hint">{{ importMessage }}</p>
              <div v-if="pending" class="import-preview">
                <h4>导入变更预览</h4>
                <p class="match-summary" role="status">已匹配 {{ pendingMatchedCount }} 项，无需逐项选择。其余 {{ fields.length - pendingMatchedCount }} 项请确认，非必填项可不登记。</p>
                <p class="hint">“将清空”表示新示例未匹配到旧字段，请重新选择或确认不登记。应用导入会清除旧的选项对应关系，避免沿用其他表的规则。</p>
                <p v-if="pending.ambiguous.length" class="issue">同名列需要你选择：{{ pending.ambiguous.join('、') }}。不会自动猜测。</p>
                <details v-for="[key, label] in fields" :key="key" class="preview-row" :open="needsAttention(key, pending.mapping, pending.columns)">
                  <summary>{{ label }} → {{ columnLabel(pending.mapping[key] || '', pending.columns) }} <span class="change-tag">{{ changeKind(key) }}</span></summary>
                  <label :for="`import-${key}`">{{ label }}目标列</label>
                  <small>原来：{{ columnLabel(settings.wechat_schema[key] || '') }}</small>
                  <select :id="`import-${key}`" :value="pending.mapping[key] || ''" :aria-label="`导入${label}目标列`" @change="pending.mapping[key] = ($event.target as HTMLSelectElement).value">
                    <option value="">不登记 / 尚未选择</option>
                    <option v-for="id in Object.keys(pending.columns)" :key="id" :value="id">{{ columnLabel(id, pending.columns) }}</option>
                  </select>
                </details>
                <p v-for="issue in pendingErrors" :key="issue" class="issue" role="alert">{{ issue }}</p>
                <div class="import-actions"><button type="button" :disabled="!!pendingErrors.length" @click="applyImport">确认应用导入</button><button type="button" @click="pending = null; importMessage = '已取消导入，原字段未修改。'">取消导入</button></div>
              </div>
            </details>
            <p v-if="!Object.keys(columns).length" class="hint">旧配置仍可使用；尚无列类型和选项信息，无法完整校验。建议先导入请求示例。</p>
            <p class="match-summary">已配置 {{ matchedCount }} 项。已对应的列无需调整，展开可修改；未配置的非必填项不会登记。</p>
            <div class="mapping-grid">
              <details v-for="[key, label] in fields" :key="key" class="field-card" :open="needsAttention(key)">
                <summary>{{ label }} <span class="field-status">{{ needsAttention(key) ? (settings.wechat_schema[key] || key === 'title' ? '需要确认' : '未配置 · 可不登记') : '已对应' }}</span><span class="column-target">{{ columnLabel(settings.wechat_schema[key] || '') }}</span></summary>
                <label :for="`wechat-field-${key}`">{{ label }}{{ key === 'title' ? ' *' : '' }}</label>
                <select :id="`wechat-field-${key}`" :value="settings.wechat_schema[key] || ''" :disabled="!!pending" :aria-label="`${label}目标列`" @change="settings.wechat_schema[key] = ($event.target as HTMLSelectElement).value; fieldChanged(key)">
                  <option value="">不登记 / 尚未选择</option>
                  <option v-if="settings.wechat_schema[key] && !columns[settings.wechat_schema[key]!]" :value="settings.wechat_schema[key]">{{ columnLabel(settings.wechat_schema[key]!) }}</option>
                  <option v-for="id in Object.keys(columns)" :key="id" :value="id">{{ columnLabel(id) }}</option>
                </select>
                <p v-if="settings.wechat_schema[key] && !columns[settings.wechat_schema[key]!]?.type" class="hint">类型未提供，按原格式发送。</p>
                <template v-if="columns[settings.wechat_schema[key] || '']?.type === 'single_select'">
                  <p class="hint">同名选项自动使用，无需配置对应规则。只有叫法不同时才需要设置下方转换。</p>
                  <p class="hint">{{ choices(key) ? `允许选项：${choices(key)!.join('、') || '无可用选项'}` : '未提供枚举选项，发送时无法核对是否允许。' }}</p>
                  <details v-if="choices(key)?.length" class="value-rules">
                    <summary>{{ label }}叫法不同？设置转换（{{ Object.keys(settings.wechat_value_mappings?.[key] || {}).length }} 条）</summary>
                    <p class="hint">例如“风控部 → 风险合规部”。两边一样不用添加；不会自动猜测不同名称是否代表同一选项。</p>
                    <fieldset :disabled="!!pending">
                      <input v-model="ruleDraft[key]!.from" :aria-label="`${label}原值`" placeholder="页面提取的原值" />
                      <select v-model="ruleDraft[key]!.to" :aria-label="`${label}替换选项`"><option value="">选择目标选项</option><option v-for="choice in choices(key)" :key="choice" :value="choice">{{ choice }}</option></select>
                      <button type="button" :disabled="!ruleDraft[key]!.from.trim() || !ruleDraft[key]!.to || ruleDraft[key]!.from.trim() === ruleDraft[key]!.to" @click="addRule(key)">添加{{ label }}对应</button>
                      <p v-if="ruleDraft[key]!.from.trim() && ruleDraft[key]!.from.trim() === ruleDraft[key]!.to" class="hint">两边相同，会自动对应，无需添加规则。</p>
                      <div v-for="(target, source) in settings.wechat_value_mappings?.[key]" :key="source" class="rule">{{ source }} → {{ target }} <button type="button" :aria-label="`删除${label}对应${source}`" @click="removeRule(key, String(source))">删除</button></div>
                    </fieldset>
                  </details>
                </template>
              </details>
            </div>
            <p v-for="issue in errors" :key="issue" role="alert" class="issue">{{ issue }}</p>
            <details class="import-box"><summary>高级：手动填写字段 ID</summary><p class="hint">导入列信息后，ID必须属于该表；修改目标列会清除该项的选项对应关系。</p><div class="mapping-grid"><label v-for="[key, label] in fields" :key="key">{{ label }}<input v-model="settings.wechat_schema[key]" :disabled="!!pending" :aria-label="`${label}字段标识`" @input="fieldChanged(key)" /></label></div></details>
          </section>
          <label class="timeout" for="wechat-timeout">等待响应时间（秒）
            <input id="wechat-timeout" v-model.number="settings.wechat_timeout" type="number" min="1" max="120" @input="emit('change')" />
          </label>
        </fieldset>
      </div>
      <footer>
        <p role="status" :class="{ error }">{{ saveBlocked ? '请先确认或取消导入，并修正字段问题；项目名称必填。' : message || '保存只更新本机配置，不发送测试数据。' }}</p>
        <button type="button" class="save" :disabled="disabled || !dirty || saveBlocked" @click="emit('save')">保存设置</button>
      </footer>
    </dialog>
  </Teleport>
</template>

<style scoped>
button, input, textarea, select { font: inherit; }
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
input, textarea, select { width: 100%; border: 1px solid var(--border); padding: 9px 10px; border-radius: 6px; background: var(--bg); color: var(--text); min-width: 0; box-sizing: border-box; font-size: 12px; }
.url-row { display: flex; gap: 8px; margin-top: 8px; }
.url-row button { flex-shrink: 0; }
.mapping-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 16px; margin-top: 16px; }
.mapping-grid span { display: block; margin-bottom: 6px; }
.mapping-grid > div { min-width:0; } .mapping-grid label { margin-bottom:6px; }
.field-card { min-width:0; border:1px solid var(--border); border-radius:8px; padding:12px; }
.field-card summary { line-height:1.7; }
.field-status { color:var(--text-secondary); font-size:11px; }
.mapping-grid .field-status { display:inline; margin-left:6px; }
.mapping-grid .column-target { display:block; font-size:12px; overflow-wrap:anywhere; margin:6px 0 0; color:var(--text-secondary); }
.match-summary { padding:10px 12px; background:var(--accent-glow); border-radius:6px; font-size:12px; line-height:1.7; }
.import-preview { margin-top:16px; padding-top:14px; border-top:1px solid var(--border); }
.preview-row { padding:10px 0; border-bottom:1px solid var(--border); }
.preview-row summary { line-height:1.8; overflow-wrap:anywhere; }
.preview-row label, .preview-row small { display:block; margin:6px 0; }
.preview-row small { color:var(--text-secondary); overflow-wrap:anywhere; }
.change-tag { color:var(--accent); margin-left:8px; font-size:11px; }
.import-actions { display:flex; gap:8px; margin-top:12px; }
.issue { color:var(--error); font-size:12px; line-height:1.7; margin-top:8px; }
.value-rules { margin-top:8px; } .value-rules fieldset { gap:6px; margin-top:8px; }
.rule { overflow-wrap:anywhere; font-size:12px; }
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
