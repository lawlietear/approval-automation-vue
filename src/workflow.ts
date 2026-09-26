export interface Department { id: string; name: string }
export interface WorkflowSettings {
  debug_enabled: boolean
  debug_steps: number
  show_department: boolean
  department_id: string
  departments: Department[]
  source: string
}
export interface DebugResult {
  source: string
  departments: { items: Department[]; complete: boolean; pages: string | null } | null
  checks: string[]
}
export const defaultWorkflow = (): WorkflowSettings => ({
  debug_enabled: false, debug_steps: 0, show_department: false,
  department_id: '', departments: [], source: '',
})
