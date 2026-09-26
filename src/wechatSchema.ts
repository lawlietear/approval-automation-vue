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

export function parseWechatSchema(input: string) {
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
  const missing: string[] = []
  const ambiguous: string[] = []
  const normalize = (name: string) => name.trim().replace(/[：:]$/, '').trim()
  for (const [key, label, ...aliases] of wechatFields) {
    const direct = schema[key]
    if (typeof direct === 'string' && direct.trim()) {
      result[key] = direct.trim()
      continue
    }
    const names: readonly string[] = [label, ...aliases]
    const matches = Object.entries(schema).filter(([id, field]) => {
      const title = object(field) ? field.title : field
      return id.trim() && typeof title === 'string' && names.includes(normalize(title))
    })
    if (matches.length === 1) result[key] = matches[0]![0].trim()
    else if (matches.length > 1) ambiguous.push(label)
    else missing.push(label)
  }
  if (ambiguous.length) throw new Error(`存在同名字段：${ambiguous.join('、')}，请保留目标列后重新导入。原字段未修改。`)
  if (!Object.keys(result).length) throw new Error('未识别到登记字段。请检查 schema 内的 title 是否为项目名称、部门等列名。原字段未修改。')
  if (new Set(Object.values(result)).size !== Object.keys(result).length) {
    throw new Error('多个登记字段对应同一字段标识，请核对示例。原字段未修改。')
  }
  return { mapping: result, missing }
}
