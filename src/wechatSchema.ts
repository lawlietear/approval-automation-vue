export const wechatFields = [
  ['title', '项目名称', '事项名称'], ['time', '时间', '登记时间', '日期'],
  ['dept', '部门'], ['biz_type', '业务类型'], ['work_type', '工作类型'],
  ['qty', '数量'], ['remark', '备注'], ['counterparty', '交易对手'],
  ['contract_amount', '合同金额', '金额'], ['contract_name', '合同名称'],
  ['contract_no', '合同编号'],
] as const

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

export interface WechatColumn { title: string; type: string; enum?: string[] }
export interface SchemaAnalysis {
  mapping: Record<string, string>
  columns: Record<string, WechatColumn>
  missing: string[]
  ambiguous: string[]
}
export const typeNames: Record<string, string> = { text: '文本', number: '数字', date_time: '日期时间', single_select: '单选' }
export function fieldTypeError(key: string, column?: WechatColumn): string {
  if (!column?.type) return ''
  const allowed = key === 'time' ? ['date_time'] : key === 'title' ? ['text']
    : ['qty', 'contract_amount'].includes(key) ? ['text', 'number'] : ['text', 'single_select']
  return allowed.includes(column.type) ? '' : `目标列为${typeNames[column.type] || column.type}，此项支持${allowed.map(t => typeNames[t]).join('、')}`
}

export function analyzeWechatSchema(input: string): SchemaAnalysis {
  // Remove presentation wrappers only; never evaluate pasted code or sample records.
  let text = input.trim().replace(/(?:&#(?:x20|32);|&nbsp;)\s*$/gi, '').trim()
  text = text.replace(/^```(?:json)?\s*\n?([\s\S]*?)\n?```$/i, '$1').trim()
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    try {
      // Markdown sometimes adds an invalid JSON escape before underscores.
      value = JSON.parse(text.replace(/(?<!\\)\\_/g, '_'))
    } catch {
      throw new Error('JSON 格式不完整或存在语法错误，请复制完整的请求示例。原字段未修改。')
    }
  }
  if (!object(value)) throw new Error('示例应为包含 schema 的 JSON 对象。原字段未修改。')
  const schema = object(value.webhook) ? value.webhook.schema : (value.schema ?? value)
  if (!object(schema)) throw new Error('schema 应为字段标识和字段说明组成的对象。原字段未修改。')
  const result: Record<string, string> = {}
  const columns: Record<string, WechatColumn> = Object.create(null)
  const missing: string[] = []
  const ambiguous: string[] = []
  const normalize = (name: string) => name.trim().replace(/[：:]$/, '').trim()
  const keys: readonly string[] = wechatFields.map(([key]) => key)
  const entries = Object.entries(schema)
  const legacy = entries.length > 0 && entries.every(([key, field]) => keys.includes(key) && typeof field === 'string')
  for (const [rawId, field] of entries) {
    const id = (legacy ? field as string : rawId).trim()
    if (!id) continue
    if (Object.hasOwn(columns, id)) throw new Error('多个登记字段对应同一字段标识。原字段未修改。')
    const title = legacy ? (rawId === 'contract_amount' ? '金额' : wechatFields.find(([key]) => key === rawId)?.[1]) : object(field) ? field.title : field
    if (typeof title !== 'string' || !title.trim()) throw new Error('列名缺失或格式无效。原字段未修改。')
    const type = !legacy && object(field) ? field.type : ''
    if (type !== undefined && typeof type !== 'string') throw new Error('字段类型格式无效。原字段未修改。')
    const choices = !legacy && object(field) ? field.enum : undefined
    if (choices !== undefined && (!Array.isArray(choices) || choices.some(v => typeof v !== 'string' || !v.trim()) || new Set(choices).size !== choices.length)) {
      throw new Error('下拉选项应为不重复的文字列表。原字段未修改。')
    }
    columns[id] = { title: title.trim(), type: (type || '').trim(), ...(choices !== undefined ? { enum: choices as string[] } : {}) }
  }
  for (const [key, label, ...aliases] of wechatFields) {
    const direct = legacy ? schema[key] : undefined
    if (typeof direct === 'string' && direct.trim()) {
      result[key] = direct.trim()
      continue
    }
    const names: readonly string[] = [label, ...aliases]
    const matches = Object.entries(columns).filter(([, field]) => names.includes(normalize(field.title)))
    if (matches.length === 1) result[key] = matches[0]![0].trim()
    else if (matches.length > 1) ambiguous.push(label)
    else missing.push(label)
  }
  if (!Object.keys(columns).length) throw new Error('未识别到有效的表格列。原字段未修改。')
  if (new Set(Object.values(result)).size !== Object.keys(result).length) {
    throw new Error('多个登记字段对应同一字段标识，请核对示例。原字段未修改。')
  }
  return { mapping: result, missing, columns, ambiguous }
}

// Legacy callers keep their strict contract; the visual importer resolves ambiguity.
export function parseWechatSchema(input: string) {
  const { mapping, missing, ambiguous } = analyzeWechatSchema(input)
  if (ambiguous.length) throw new Error(`存在同名字段：${ambiguous.join('、')}，请在列选择中确认。原字段未修改。`)
  if (!Object.keys(mapping).length) throw new Error('未识别到登记字段。原字段未修改。')
  return { mapping, missing }
}
