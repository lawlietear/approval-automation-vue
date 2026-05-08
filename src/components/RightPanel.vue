<script setup lang="ts">
interface FieldDef {
  label: string
  key: string
  barClass: string
  highlight?: boolean
}

const FIELDS: FieldDef[] = [
  { label: 'dept', key: '部门', barClass: 'c-dept' },
  { label: 'item', key: '事项名称', barClass: 'c-item' },
  { label: 'work', key: '工作类型', barClass: 'c-work' },
  { label: 'biz', key: '业务类型', barClass: 'c-biz' },
  { label: 'party', key: '交易对手', barClass: 'c-party' },
  { label: 'amount', key: '合同金额', barClass: 'c-amt', highlight: true },
  { label: 'contract', key: '合同名称', barClass: 'c-contract' },
  { label: 'id', key: '合同编号', barClass: 'c-id' },
  { label: 'qty', key: '数量', barClass: 'c-qty' },
  { label: 'note', key: '备注', barClass: 'c-note' },
]

const props = defineProps<{
  view: 'empty' | 'loading' | 'data'
  dataMap: Record<string, string>
  pageSub: string
}>()
</script>

<template>
  <div class="main">
    <div class="main-content">
      <div class="page-header">
        <div class="page-title">审批预览</div>
        <div class="page-sub">{{ pageSub }}</div>
      </div>

      <div v-if="view === 'empty'" class="empty-state show">
        <div class="empty-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 8v13H3V8"/>
            <path d="M1 3h22v5H1z"/>
            <path d="M10 12h4"/>
          </svg>
        </div>
        <div class="empty-title">no data</div>
        <div class="empty-sub">connect chrome and choose a system to start</div>
      </div>

      <div v-else-if="view === 'loading'" class="skeleton show">
        <div class="skeleton-row"></div>
        <div class="skeleton-row"></div>
        <div class="skeleton-row"></div>
        <div class="skeleton-row"></div>
        <div class="skeleton-row"></div>
        <div class="skeleton-row"></div>
      </div>

      <div v-else class="card">
        <div class="data-list">
          <div
            v-for="f in FIELDS"
            :key="f.key"
            class="data-row"
          >
            <div class="data-label" :class="f.barClass">{{ f.label }}</div>
            <div class="data-value" :class="{ highlight: f.highlight }" :title="dataMap[f.key] || ''">
              {{ dataMap[f.key] || '-' }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}
.main-content {
  flex: 1;
  padding: 28px 32px;
  overflow-y: auto;
}
.page-header {
  margin-bottom: 24px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
  transition: border-color 0.3s ease;
}
.page-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 2px;
  transition: color 0.3s ease;
}
.page-sub { font-size: 11px; color: var(--text-secondary); font-weight: 400; transition: color 0.3s ease; }

.card {
  background: rgba(var(--card-rgb), 0.38);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(var(--text-rgb), 0.09);
  box-shadow: inset 0 1px 0 0 rgba(255,255,255,0.04);
  border-radius: 8px;
  padding: 24px;
  transition: background 0.3s ease, border-color 0.3s ease;
}
.data-list { display: flex; flex-direction: column; gap: 0; }
.data-row {
  display: flex;
  align-items: baseline;
  padding: 12px 0;
  border-bottom: 1px solid var(--divider);
  gap: 14px;
  transition: border-color 0.3s ease;
}
.data-row:last-child { border-bottom: none; }
.data-label {
  width: 90px;
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.data-label::before {
  content: '';
  width: 2px;
  height: 14px;
  border-radius: 1px;
  display: inline-block;
  flex-shrink: 0;
}
.data-value {
  flex: 1;
  font-size: 13px;
  color: var(--text);
  font-weight: 400;
  transition: color 0.3s ease;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.data-value.highlight {
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  font-weight: 700;
  color: var(--accent);
  transition: color 0.3s ease;
}

.c-amt::before { background: var(--accent); }
.c-dept::before { background: #b45309; }
.c-biz::before { background: #92400e; }
.c-item::before { background: #78350f; }
.c-contract::before { background: #9a3412; }
.c-id::before { background: #c2410c; }
.c-work::before { background: #ea580c; }
.c-party::before { background: #f97316; }
.c-qty::before { background: #fb923c; }
.c-note::before { background: var(--text-secondary); }

/* Empty State */
.empty-state {
  display: none;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 40px;
  text-align: center;
}
.empty-state.show { display: flex; }
.empty-icon {
  width: 64px;
  height: 64px;
  margin-bottom: 20px;
  color: var(--text-secondary);
  animation: float-y 4s ease-in-out infinite;
}
.empty-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 15px;
  color: var(--text-tertiary);
  font-weight: 700;
  margin-bottom: 6px;
  animation: fade-up 0.6s ease-out both;
}
.empty-sub {
  animation: fade-up 0.6s ease-out 0.15s both;
}
@keyframes float-y {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}
@keyframes fade-up {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.empty-sub {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 400;
}

/* Skeleton Loading */
.skeleton {
  display: none;
  flex-direction: column;
  gap: 12px;
  padding: 8px 0;
}
.skeleton.show { display: flex; }
.skeleton-row {
  height: 44px;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--skeleton-1) 25%, var(--skeleton-2) 50%, var(--skeleton-1) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.6s infinite;
}
.skeleton-row:nth-child(2) { animation-delay: 0.1s; width: 92%; }
.skeleton-row:nth-child(3) { animation-delay: 0.2s; width: 85%; }
.skeleton-row:nth-child(4) { animation-delay: 0.3s; width: 96%; }
.skeleton-row:nth-child(5) { animation-delay: 0.4s; width: 78%; }
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Staggered reveal */
@keyframes slideIn {
  from { opacity: 0; transform: translateX(12px); }
  to   { opacity: 1; transform: translateX(0); }
}
.data-row {
  animation: slideIn 0.45s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.data-row:nth-child(1) { animation-delay: 0ms; }
.data-row:nth-child(2) { animation-delay: 55ms; }
.data-row:nth-child(3) { animation-delay: 110ms; }
.data-row:nth-child(4) { animation-delay: 165ms; }
.data-row:nth-child(5) { animation-delay: 220ms; }
.data-row:nth-child(6) { animation-delay: 275ms; }
.data-row:nth-child(7) { animation-delay: 330ms; }
.data-row:nth-child(8) { animation-delay: 385ms; }
.data-row:nth-child(9) { animation-delay: 440ms; }
.data-row:nth-child(10) { animation-delay: 495ms; }
</style>
