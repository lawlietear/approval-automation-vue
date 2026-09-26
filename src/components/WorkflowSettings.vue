<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { defaultWorkflow, type WorkflowSettings, type DebugResult } from '../workflow'

const props = defineProps<{ isRunning: boolean; canInspect: boolean; saved: WorkflowSettings; result: DebugResult | null }>()
const emit = defineEmits<{ busy: [value: boolean]; changed: [value: WorkflowSettings]; inspect: [] }>()
const draft = ref(defaultWorkflow())
const loaded = ref(false)
const dirty = ref(false)
const saving = ref(false)
const message = ref('正在读取设置…')
function changed() { dirty.value = true; emit('busy', true); message.value = '修改后请保存，再开始运行。' }
const copySettings = (value: WorkflowSettings): WorkflowSettings => JSON.parse(JSON.stringify(value))
watch(() => props.saved, value => { if (!dirty.value) draft.value = copySettings(value) })
watch(() => props.result, result => {
  if (!result) return
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
    message.value = result.departments ? '当前仅为部分选项，不替换已保存列表。请由用户检查分页；本版本不自动翻页。' : '未发现部门窗口，请由用户手动打开后重新读取。'
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
    <p class="safety">安全边界：只读取与检查可点击性，不发送真实点击，不审批、不登记。中间“确定”也可能直接提交，步骤数不会解除保护。</p>
    <fieldset :disabled="!loaded || isRunning || saving">
      <label class="switch"><input type="checkbox" v-model="draft.debug_enabled" @change="changed">启用安全调试模式（仅核心系统）</label>
      <label for="debug-steps">用户确认：当前流程预计需要几步完成审批？</label>
      <select id="debug-steps" v-model.number="draft.debug_steps" @change="changed">
        <option :value="0">尚未确认</option><option v-for="n in 10" :key="n" :value="n">{{ n }} 步{{ n === 1 ? '：不点击同意' : '：仍不点击可能提交的步骤' }}</option>
      </select>
      <div class="department-heading"><h4>部门选项</h4><button :disabled="!canInspect" @click="emit('inspect')">读取已打开的部门窗口</button></div>
      <p>请由用户手动打开“选择部门”窗口。读取不会点击同意、中间确认、部门选项或最终确定。</p>
      <label for="default-department">正式审批默认选择</label>
      <select id="default-department" v-model="draft.department_id" @change="changed">
        <option value="">沿用原配置（未指定部门 ID）</option>
        <option v-for="item in draft.departments" :key="item.id" :value="item.id">{{ item.name }} · {{ item.id }}</option>
      </select>
      <p v-if="draft.source">选项来源：{{ draft.source }}。运行时会再次核对当前窗口，不按旧行号点击。</p>
      <label class="switch"><input type="checkbox" v-model="draft.show_department" @change="changed">在首页显示部门选择</label>
      <button class="primary" :disabled="!dirty || (draft.debug_enabled && !draft.debug_steps)" @click="save">保存调试与部门设置</button>
    </fieldset>
    <p role="status">{{ message }}</p>
    <div v-if="result" class="report"><h4>最近一次检查 · 未发送点击</h4><p v-for="check in result.checks" :key="check">{{ check }}</p>
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
</style>
