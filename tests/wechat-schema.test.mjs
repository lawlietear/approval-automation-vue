import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseWechatSchema, analyzeWechatSchema, fieldTypeError } from '../src/wechatSchema.ts'

const schema = {
  f736Lk: { title: '时间', type: 'date_time' },
  fVgYr2: { title: '部门', type: 'single_select', enum: ['股权投资部', '风险合规部'] },
  fa6P3k: { title: '项目名称', type: 'text' },
  fjTNHN: { title: '业务类型', type: 'single_select', enum: ['金融不良资产'] },
  fjXqjX: { title: '工作类型', type: 'single_select', enum: ['合同审批'] },
  fxy0gT: { title: '数量', type: 'number' },
  fyY3Ni: { title: '备注', type: 'text' },
  fUCTwp: { title: '交易对手', type: 'text' },
  fMAzZf: { title: '金额', type: 'text' },
  fp8OzH: { title: '合同名称', type: 'text' },
  fJ6kHY: { title: '合同编号', type: 'text' },
}
const expected = {
  title: 'fa6P3k', time: 'f736Lk', dept: 'fVgYr2', biz_type: 'fjTNHN',
  work_type: 'fjXqjX', qty: 'fxy0gT', remark: 'fyY3Ni', counterparty: 'fUCTwp',
  contract_amount: 'fMAzZf', contract_name: 'fp8OzH', contract_no: 'fJ6kHY',
}
test('full request matches all eleven fields and ignores example values', () => {
  assert.deepEqual(parseWechatSchema(JSON.stringify({schema, add_records: [{values: {fa6P3k: '测试文本'}}]})), {mapping: expected, missing: []})
})
test('raw schema, legacy config and simple mapping remain supported', () => {
  assert.deepEqual(parseWechatSchema(JSON.stringify(schema)).mapping, expected)
  assert.deepEqual(parseWechatSchema(JSON.stringify({webhook: {schema: expected}})).mapping, expected)
  assert.equal(parseWechatSchema('{"schema":{"a":"事项名称","b":"日期"}}').mapping.time, 'b')
  assert.equal(analyzeWechatSchema(JSON.stringify({webhook:{schema:expected}})).columns.fMAzZf.title, '金额')
})
test('Markdown wrappers and escaped underscores from copied requests', () => {
  const pasted = '```json\n' + JSON.stringify({schema}).replaceAll('_', '\\_') + '\n``` &#x20;'
  assert.deepEqual(parseWechatSchema(pasted).mapping, expected)
})
test('trim labels and report missing fields', () => {
  const result = parseWechatSchema('{"schema":{"a":{"title":" 项目名称： "},"b":{"title":"未知"}}}')
  assert.deepEqual(result.mapping, {title: 'a'})
  assert.ok(result.missing.includes('合同金额'))
})
test('ambiguous names and duplicate IDs require correction', () => {
  assert.throws(() => parseWechatSchema('{"schema":{"a":{"title":"项目名称"},"b":{"title":"事项名称"}}}'), /同名/)
  assert.throws(() => parseWechatSchema('{"schema":{"title":"same","dept":"same"}}'), /同一字段/)
})
test('malformed and unrelated input has actionable errors', () => {
  for (const input of ['null', '[]', '{"schema":null}', '{"schema":{"x":{"type":"text"}}}', 'bad json']) {
    assert.throws(() => parseWechatSchema(input), /原字段未修改/)
  }
})

test('visual analysis retains types/options and lets the user resolve duplicate names', () => {
  const result = analyzeWechatSchema(JSON.stringify({schema:{...schema, other: {title:'事项名称', type:'text'}}}))
  assert.deepEqual(result.ambiguous, ['项目名称'])
  assert.equal(result.mapping.title, undefined)
  assert.equal(result.columns.other.title, '事项名称')
  assert.deepEqual(result.columns.fVgYr2.enum, ['股权投资部', '风险合规部'])
  assert.equal(result.columns.f736Lk.type, 'date_time')
})

test('unmatched titles remain available for manual column selection', () => {
  const result = analyzeWechatSchema('{"schema":{"a":{"title":"自定义事项列","type":"text"}}}')
  assert.deepEqual(result.mapping, {})
  assert.equal(result.columns.a.title, '自定义事项列')
})

test('unsupported types are reported, missing types preserve legacy behavior', () => {
  assert.match(fieldTypeError('title', {title:'标题',type:'number'}), /不兼容|支持/)
  assert.match(fieldTypeError('dept', {title:'部门',type:'multi_select'}), /multi_select/)
  assert.equal(fieldTypeError('contract_amount', {title:'金额',type:'number'}), '')
  assert.equal(fieldTypeError('dept', {title:'部门',type:''}), '')
})

test('invalid options and normalized duplicate IDs cannot destroy old settings', () => {
  for (const fields of [
    {a:{title:'部门',type:'single_select',enum:['A','A']}},
    {a:{title:'部门',type:'single_select',enum:[{text:'A'}]}},
    {a:{title:'事项名称'}, ' a ':{title:'备注'}},
  ]) assert.throws(() => analyzeWechatSchema(JSON.stringify({schema:fields})), /原字段未修改/)
})
