<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { defaultWorkflow, type WorkflowSettings, type DebugResult } from '../workflow'

const props = defineProps<{ isRunning: boolean; canInspect: boolean; saved: WorkflowSettings; result: DebugResult | null; error: string }>()
const emit = defineEmits<{ busy: [value: boolean]; changed: [value: WorkflowSettings]; inspect: [] }>()
const draft = ref(defaultWorkflow())
const loaded = ref(false)
const dirty = ref(false)
const saving = ref(false)
const message = ref('正在读取设置…')
const errorNotice = ref<HTMLElement | null>(null)
watch(() => props.error, async error => {
  if (error) { await nextTick(); errorNotice.value?.scrollIntoView({ block: 'nearest' }) }
})
function changed() { dirty.value = true; emit('busy', true); message.value = '修改后请保存，再开始运行。' }
const copySettings = (value: WorkflowSettings): WorkflowSettings => JSON.parse(JSON.stringify(value))
watch(() => props.saved, value => { if (!dirty.value) draft.value = copySettings(value) })
watch(() => props.result, result => {
  if (!result) { message.value = ''; return }
  if (result.departments?.complete) {
    const items = result.departments.items.map(({ id, name }) => ({ id, name }))
    if (draft.value.source === result.source && JSON.stringify(draft.value.departments) === JSON.stringify(items)) {
      message.value = '当前窗口选项与已读取列表一致。'
      return
    }
    draft.value.departments = items
    draft.value.source = result.source
    if (!draft.value.departments.some(item => item.id === draft.value.department_id)) draft.value.department_id = ''
    changed()
    message.value = `已读取完整的 ${draft.value.departments.length} 个选项，请选择并保存。`
  } else {
    message.value = result.departments ? '当前窗口仅为部分选项，不替换已保存列表；请点击“实时读取部门”获取完整列表。' : '本次已检查项目信息；需要选择部门时，请点击“实时读取部门”，无需打开原审批弹窗。'
  }
})
onMounted(async () => {
  emit('busy', true)
  try {
    draft.value = await invoke<WorkflowSettings>('get_workflow_settings')
    loaded.value = true
    emit('changed', copySettings(draft.value))
    emit('busy', false)
    message.value = ''
  } catch (error) { message.value = `设置读取失败：${error}。未允许审批。` }
})
async function save() {
  saving.value = true
  try {
    await invoke('save_workflow_settings', { settings: draft.value })
    dirty.value = false
    emit('changed', copySettings(draft.value))
    emit('busy', false)
    message.value = '已保存，下次运行生效。'
  } catch (error) { message.value = String(error) }
  finally { saving.value = false }
}
</script>

<template>
  <section class="workflow-settings">
    <h3>调试与部门选择</h3>
    <p class="safety">调试仅检查项目信息和可点击性，不推进审批。“实时读取部门”通过当前登录会话查询部门，在本软件中选择保存，不打开带提交回调的原审批弹窗。</p>
    <fieldset :disabled="!loaded || isRunning || saving">
      <label class="switch"><input type="checkbox" v-model="draft.debug_enabled" @change="changed">启用安全调试模式（仅核心系统）</label>
      <label for="debug-steps">预计审批步骤数（仅记录，不控制执行）</label>
      <select id="debug-steps" v-model.number="draft.debug_steps" @change="changed">
        <option :value="0">尚未确认</option><option v-for="n in 10" :key="n" :value="n">{{ n }} 步（只读检查，不自动执行）</option>
      </select>
      <div class="department-heading"><h4>部门选项</h4><button :disabled="!canInspect || dirty" @click="emit('inspect')">实时读取部门</button></div>
      <p>连接浏览器并打开一个核心项目详情即可，无需点击“通过”。读取成功后选择部门并保存；正式审批仍需另行触发。修改未保存时，请先保存。</p>
      <p v-if="isRunning" role="status">正在检查，请等待本次结果…</p>
      <p v-else-if="error" ref="errorNotice" role="alert" class="read-error">{{ error }}<br>本次未取得新选项，已保存的设置不变。</p>
      <label for="default-department">正式审批默认选择</label>
      <select id="default-department" v-model="draft.department_id" @change="changed">
        <option value="">沿用原配置（未指定部门 ID）</option>
        <option v-for="item in draft.departments" :key="item.id" :value="item.id">{{ item.name }} · {{ item.id }}</option>
      </select>
      <p v-if="draft.source">选项来源：{{ draft.source }}。运行时会再次核对当前窗口，不按旧行号点击。</p>
      <label class="switch"><input type="checkbox" v-model="draft.show_department" @change="changed">在首页显示部门选择</label>
      <button class="primary" :disabled="!dirty || (draft.debug_enabled && !draft.debug_steps)" @click="save">保存调试与部门设置</button>
    </fieldset>
    <p v-if="!error && !isRunning" role="status">{{ message }}</p>
    <div v-if="result && !error && !isRunning" class="report"><h4>本次检查 · 未发送点击</h4><p v-for="check in result.checks" :key="check">{{ check }}</p>
      <p v-if="result.departments && !result.departments.complete">仅当前页：{{ result.departments.items.map(item => item.name).join('、') }}（不是全部选项）</p>
    </div>
  </section>
</template>

<style scoped>
h3 { font-size:17px; margin-bottom:12px; } h4 { font-size:13px; }
p { font-size:12px; color:var(--text-secondary); line-height:1.75; margin:8px 0; overflow-wrap:anywhere; }
.safety,.report { padding:12px 14px; background:var(--accent-glow); border-left:2px solid var(--accent); border-radius:0 8px 8px 0; }
fieldset { border:0; min-width:0; } label { display:block; margin:16px 0 6px; font-size:13px; }
.switch { display:flex; gap:9px; align-items:center; } input { accent-color:var(--accent); }
select { width:100%; padding:9px; border:1px solid var(--border); border-radius:6px; background:var(--bg); color:var(--text); font:inherit; }
.department-heading { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px; border-top:1px solid var(--border); padding-top:18px; margin-top:20px; }
button { padding:9px 12px; border-radius:6px; border:1px solid var(--border); color:var(--text); background:var(--panel); cursor:pointer; font:inherit; font-size:12px; }
button.primary { background:var(--accent); color:#fff; margin-top:12px; } button:disabled { opacity:.5; cursor:not-allowed; }
.report { margin-top:14px; }
.read-error { color:var(--text); border-left:3px solid var(--accent); padding:10px 12px; background:var(--accent-glow); }
</style>
