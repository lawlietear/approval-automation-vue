<script setup lang="ts">
import { ref } from 'vue'
import { invoke } from '@tauri-apps/api/core'

type Channel = { state: string; detail: string; attempts: number }
type Item = { id: string; revision: string; created: string; system: string; department: string; task_id: string; approval: string; note: string; records: { data: Record<string, unknown>; channels: Record<string, Channel> }[] }
type Check = { name: string; status: string; message: string }
const props = defineProps<{ disabled: boolean; mutationDisabled: boolean; endpoint: string }>()
const emit = defineEmits<{ busy: [value: boolean] }>()
const dialog = ref<HTMLDialogElement>()
const mode = ref<'list' | 'diagnose'>('list')
const busy = ref(false)
const items = ref<Item[]>([])
const checks = ref<Check[]>([])
const offset = ref(0)
const more = ref(false)
const error = ref('')
const confirmation = ref<{ item: Item; index: number; channel: string; action: string } | null>(null)
const labels: Record<string, string> = { pending: '未登记', sending: '结果待核实', unknown: '结果待核实', failed: '未完成', success: '已登记', disabled: '未启用' }
const approvalLabels: Record<string, string> = { unknown: '审批结果待核实', flow_returned: '操作流程已返回', confirmed: '已通过待办消失核验' }
const checkLabels: Record<string, string> = { ok: '通过', warn: '需留意', error: '需处理', skip: '未检查' }

async function call(action: string, args: Record<string, unknown> = {}) {
  busy.value = true; emit('busy', true); error.value = ''
  try { return await invoke<any>('activity_command', { action, endpoint: props.endpoint, ...args }) }
  catch (e) { error.value = String(e); return null }
  finally { busy.value = false; emit('busy', false) }
}
async function refresh() {
  confirmation.value = null
  const result = await call(mode.value, { offset: offset.value })
  if (!result) return
  if (mode.value === 'list') { items.value = result.items; more.value = result.has_more }
  else checks.value = result.checks
}
async function open(value: 'list' | 'diagnose') {
  if (props.disabled || busy.value) return
  mode.value = value; offset.value = 0; items.value = []; checks.value = []; error.value = ''
  dialog.value?.showModal()
  await refresh()
}
async function page(delta: number) { offset.value = Math.max(0, offset.value + delta); await refresh() }
async function confirm() {
  const request = confirmation.value
  if (!request || props.mutationDisabled || props.disabled || busy.value) return
  const result = await call(request.action, { itemId: request.item.id, recordIndex: request.index,
    channel: request.channel, revision: request.item.revision })
  confirmation.value = null
  if (result?.item) items.value = items.value.map(item => item.id === result.item.id ? result.item : item)
}
function close() { if (!busy.value) { confirmation.value = null; dialog.value?.close() } }
</script>

<template>
  <div class="activity-launch">
    <button :disabled="disabled || busy" @click="open('list')"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/></svg>处理记录</button>
    <button :disabled="disabled || busy" @click="open('diagnose')"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M5 12h4l2-5 3 10 2-5h3"/></svg>一键诊断</button>
  </div>
  <Teleport to="body">
    <dialog ref="dialog" class="activity-dialog" @cancel.prevent="close">
      <header><div><span class="eyebrow">{{ mode === 'list' ? '本机留痕 / 独立补登' : '只读检查 / 不触发审批' }}</span><h2>{{ mode === 'list' ? '处理记录' : '运行诊断' }}</h2></div><button :disabled="busy" @click="close">关闭</button></header>
      <div class="activity-body" :aria-busy="busy">
        <p class="intro">{{ mode === 'list' ? '只记录启用本版本后的操作。补登不重新审批，已成功通道不再发送。记录仅存本机，不随5天日志清理。' : '检查配置、浏览器及页面状态。不点击业务按钮，不试发企业微信，不创建 Obsidian 文件。' }}</p>
        <p v-if="error" role="alert" class="error">{{ error }}</p>
        <p v-if="busy" role="status">正在检查或处理，请勿关闭程序…</p>
        <template v-if="mode === 'list'">
          <p v-if="mutationDisabled" class="notice">调试模式开启或设置未就绪：可查看记录，不能补登或更改状态。</p>
          <p v-if="!items.length && !busy && !error">暂无处理记录。</p>
          <article v-for="item in items" :key="item.id" class="activity-card">
            <div class="item-heading"><time>{{ new Date(item.created).toLocaleString('zh-CN') }}</time><span>{{ item.system === 'new' ? 'OA 系统' : item.system === 'old' ? '核心系统' : '自动识别' }}</span></div>
            <strong>{{ approvalLabels[item.approval] || item.approval }}</strong><p>{{ item.note }}</p>
            <p v-if="item.department || item.task_id">审批部门 ID：{{ item.department || '沿用配置' }}<span v-if="item.task_id"> · 任务 {{ item.task_id }}</span></p>
            <p v-if="!item.records.length">未保存可补登数据，可能在审批过程中中断；请人工核实，不要重跑审批。</p>
            <section v-for="(record, index) in item.records" :key="index" class="record">
              <h3>{{ record.data['事项名称'] || '未命名事项' }}</h3>
              <details><summary>查看登记字段</summary><dl><template v-for="(value, key) in record.data" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template></dl></details>
              <div v-for="(state, channel) in record.channels" :key="channel" class="channel">
                <div><b>{{ channel }}</b><span class="badge" :class="state.state">{{ labels[state.state] || state.state }}</span><small>尝试 {{ state.attempts }} 次</small></div>
                <p v-if="state.detail">{{ state.detail }}</p>
                <div v-if="item.approval !== 'unknown'" class="actions">
                  <button v-if="['failed', 'pending'].includes(state.state)" :disabled="busy || mutationDisabled" @click="confirmation = { item, index, channel: String(channel), action: 'retry' }">仅补登{{ channel }}</button>
                  <template v-if="['sending', 'unknown'].includes(state.state)">
                    <button :disabled="busy || mutationDisabled" @click="confirmation = { item, index, channel: String(channel), action: 'received' }">已核实：存在记录</button>
                    <button :disabled="busy || mutationDisabled" @click="confirmation = { item, index, channel: String(channel), action: 'absent' }">已核实：没有记录</button>
                  </template>
                </div>
              </div>
            </section>
          </article>
          <div class="pagination"><button :disabled="busy || offset === 0" @click="page(-20)">上一页</button><span>第 {{ offset / 20 + 1 }} 页</span><button :disabled="busy || !more" @click="page(20)">下一页</button></div>
        </template>
        <div v-else class="checks"><article v-for="(check, index) in checks" :key="index" class="check" :class="check.status"><h3>{{ check.name }} <span>{{ checkLabels[check.status] }}</span></h3><p>{{ check.message }}</p></article></div>
      </div>
      <footer v-if="confirmation" class="confirmation" role="alert">
        <strong>{{ confirmation.action === 'retry' ? `仅向${confirmation.channel}补登本条记录？` : confirmation.action === 'received' ? '确认已在原目标中找到这条记录？' : '确认已核实原目标没有这条记录？' }}</strong>
        <p>{{ confirmation.action === 'retry' ? '使用当前字段映射、原处理日期；登记目标改变会被拦截，不重新审批。' : '请先手动检查表格或文件。此操作只更改本机状态，不发送数据。' }}</p>
        <button :disabled="busy" @click="confirmation = null">返回核实</button><button :disabled="busy || mutationDisabled" @click="confirm">确认{{ confirmation.action === 'retry' ? '补登' : '核实结果' }}</button>
      </footer>
      <footer v-else><span>{{ mode === 'list' ? '结果不确定时，先核实再补登。' : '诊断通过不等于审批或登记一定成功。' }}</span><button :disabled="busy" @click="refresh">{{ mode === 'list' ? '刷新记录' : '重新诊断' }}</button></footer>
    </dialog>
  </Teleport>
</template>

<style scoped>
.activity-launch { display:flex; gap:8px; margin-top:8px; }
button { border:1px solid var(--border); border-radius:7px; background:var(--panel); color:var(--text); padding:7px 11px; font:inherit; font-size:12px; cursor:pointer; }
button:disabled { opacity:.45; cursor:not-allowed; } button:hover:not(:disabled) { border-color:var(--accent); }
.activity-launch button { flex:1; display:flex; align-items:center; justify-content:center; gap:7px; }
svg { width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:1.6; }
.activity-dialog { width:min(800px, calc(100vw - 32px)); max-height:calc(100vh - 32px); margin:auto; padding:0; border:1px solid var(--border); border-radius:16px; background:var(--bg); color:var(--text); }
.activity-dialog[open] { display:flex; flex-direction:column; }.activity-dialog::backdrop { background:#17140f80; }
header,footer { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:18px 22px; flex-shrink:0; }
header { border-bottom:1px solid var(--border); } h2 { font-size:22px; margin:3px 0 0; }.eyebrow { font-size:11px; color:var(--accent); }
.activity-body { overflow:auto; padding:4px 22px 20px; min-height:80px; } p { font-size:12px; line-height:1.75; margin:7px 0; overflow-wrap:anywhere; color:var(--text-secondary); }
.intro { margin:14px 0; }.activity-card { border:1px solid var(--border); background:var(--panel); border-radius:10px; padding:16px; margin:12px 0; }
.item-heading { display:flex; justify-content:space-between; gap:8px; font-size:11px; color:var(--text-secondary); margin-bottom:10px; }
.record { border-top:1px solid var(--border); margin-top:12px; padding-top:12px; } h3 { font-size:14px; line-height:1.6; margin:0; overflow-wrap:anywhere; }
details { margin-top:8px; font-size:12px; } summary { cursor:pointer; color:var(--accent); } dl { display:grid; grid-template-columns:85px 1fr; gap:8px; margin:12px 0; } dt { color:var(--text-secondary); } dd { margin:0; white-space:pre-wrap; overflow-wrap:anywhere; }
.channel { padding:10px 0; }.channel b { font-size:12px; }.badge { display:inline-block; margin:0 8px; padding:2px 7px; background:var(--accent-glow); color:var(--accent); border-radius:4px; font-size:11px; }.badge.success { color:#087568; background:#0c9b8114; } small { color:var(--text-secondary); font-size:10px; }.actions { display:flex; flex-wrap:wrap; gap:6px; }
footer { border-top:1px solid var(--border); font-size:12px; } .confirmation { display:block; background:var(--accent-glow); }.confirmation button { margin-right:8px; }
.pagination { display:flex; justify-content:center; gap:16px; align-items:center; font-size:12px; }
.check { border-left:3px solid var(--border); padding:10px 14px; margin-top:12px; background:var(--panel); }.check.ok { border-color:#149d8b; }.check.warn,.check.error { border-color:var(--accent); }.check h3 span { float:right; font-size:11px; color:var(--text-secondary); }.error { color:#ae3d27; }.notice { background:var(--accent-glow); padding:10px; }
</style>
