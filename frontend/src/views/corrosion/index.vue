<template>
  <section class="page" data-module="corrosion">
    <header class="page-head">
      <div>
        <h2>防腐检测评级整改跟踪</h2>
        <p class="page-desc">连接防腐记录、检测管段、防腐层类型和破损点数量；边界点数、停用管段、重复证据均保留同一次判定并禁止自动关闭。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记防腐记录</button>
        <button class="btn" type="button" @click="exportRows">导出防腐检测清单</button>
      </div>
    </header>

    <div class="tab-row">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-button"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <div v-if="activeTab === 'overview'" class="tab-panel">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">判定总数</span>
          <strong class="stat-value">{{ ratingSummary.total ?? 0 }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">待整改/整改中</span>
          <strong class="stat-value">{{ ratingSummary.pendingRectification ?? 0 }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">禁止自动关闭</span>
          <strong class="stat-value warn">{{ ratingSummary.blockedAutoClose ?? 0 }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">整改证据重复</span>
          <strong class="stat-value warn">{{ ratingSummary.reusedEvidence ?? 0 }}</strong>
        </article>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in ratingColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in ratingSummary.items ?? []" :key="String(row['评级'])">
            <td v-for="column in ratingColumns" :key="column">{{ formatValue(row[column]) }}</td>
          </tr>
        </tbody>
      </table>

      <h3>同一次评级判定</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in sharedDecisionColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in ratingSummary.tracks ?? []" :key="String(row.id)">
            <td v-for="column in sharedDecisionColumns" :key="column">
              <span v-if="column === '禁止自动关闭' && row[column]" class="risk-badge">禁止</span>
              <template v-else>{{ formatValue(row[column]) }}</template>
            </td>
          </tr>
          <tr v-if="!(ratingSummary.tracks ?? []).length">
            <td :colspan="sharedDecisionColumns.length" class="empty-state">暂无已检测评级判定</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="activeTab === 'detail'" class="tab-panel">
      <form class="filter-bar" @submit.prevent="reload">
        <label class="filter-item filter-wide">
          <span>记录编号 / 检测管段 / 防腐层类型</span>
          <input v-model="detailKeyword" placeholder="输入关键字检索关联记录" />
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetDetailFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in detailColumns" :key="column">{{ column }}</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in detailRows" :key="String(row.id)">
            <td v-for="column in detailColumns" :key="column" :title="column === '拦截原因' ? formatValue(row[column]) : ''">
              <span v-if="column === '禁止自动关闭' && row[column]" class="risk-badge">禁止</span>
              <template v-else>{{ formatValue(row[column]) }}</template>
            </td>
            <td class="row-actions action-cell">
              <button
                v-for="action in availableActions(row)"
                :key="action"
                class="link"
                :class="{ danger: action === '确认修复' && row['禁止自动关闭'] }"
                type="button"
                @click="runWorkflow(action, row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
          <tr v-if="!detailRows.length">
            <td :colspan="detailColumns.length + 1" class="empty-state">暂无防腐检测数据，可先登记防腐记录</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot">
        <span>共 {{ detailTotal }} 条防腐检测记录</span>
      </footer>
    </div>

    <div v-if="activeTab === 'progress'" class="tab-panel">
      <form class="filter-bar" @submit.prevent="reload">
        <label class="filter-item filter-wide">
          <span>判定编号 / 防腐记录 / 检测管段 / 防腐层类型</span>
          <input v-model="progressKeyword" placeholder="输入整改跟踪关键字" />
        </label>
        <select v-model="progressFilter" class="filter-select">
          <option value="">全部进度</option>
          <option v-for="item in progressOptions" :key="item" :value="item">{{ item }}</option>
        </select>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetProgressFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in progressColumns" :key="column">{{ column }}</th>
            <th>跟踪动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in progressRows" :key="String(row.id)">
            <td v-for="column in progressColumns" :key="column" :title="column === '拦截原因' ? formatValue(row[column]) : ''">
              <span v-if="column === '禁止自动关闭' && row[column]" class="risk-badge">禁止</span>
              <template v-else>{{ formatValue(row[column]) }}</template>
            </td>
            <td class="row-actions action-cell">
              <button class="link" type="button" @click="runWorkflow('提交整改证据', row)">提交整改证据</button>
              <button class="link" type="button" @click="runWorkflow('补充评级依据', row)">补充评级依据</button>
              <button class="link danger" type="button" @click="runWorkflow('确认修复', row)">确认修复</button>
              <button class="link" type="button" @click="runWorkflow('人工核验关闭', row)">人工核验关闭</button>
            </td>
          </tr>
          <tr v-if="!progressRows.length">
            <td :colspan="progressColumns.length + 1" class="empty-state">暂无整改跟踪记录</td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer class="page-foot">
      <span>判定编号在评级总览、检测详情和整改进度中保持一致</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type CellValue = string | number | boolean | string[] | null
type Row = Record<string, CellValue>
type ActionResponse = { ok: boolean; message: string; entry: Row | null }
type RatingOverview = {
  items: Row[]
  tracks: Row[]
  total: number
  pendingRectification: number
  blockedAutoClose: number
  reusedEvidence: number
}

const ENDPOINT = '/api/corrosion'
const tabs = [
  { key: 'overview', label: '评级总览' },
  { key: 'detail', label: '检测详情' },
  { key: 'progress', label: '整改进度' },
] as const

const ratingColumns = ['评级', '数量', '待整改', '整改中', '已关闭', '禁止自动关闭']
const sharedDecisionColumns = [
  '判定编号', '判定版本', '记录编号', '检测管段', '防腐层类型', '破损点数量',
  '防腐评级', '完整评级依据', '禁止自动关闭', '拦截原因', '整改进度',
]
const detailColumns = [
  '记录编号', '检测管段', '防腐层类型', '破损点数量', '管地电位', '检测日期', '检测人员',
  '记录状态', '判定编号', '判定版本', '防腐评级', '完整评级依据', '禁止自动关闭', '拦截原因', '整改进度',
]
const progressColumns = [
  '判定编号', '判定版本', '记录编号', '检测管段', '防腐层类型', '破损点数量', '防腐评级',
  '完整评级依据', '人工评级依据', '整改证据', '整改证据重复使用', '禁止自动关闭', '拦截原因',
  '整改进度', '关闭方式', '关闭时间',
]
const progressOptions = ['待评级', '待整改', '整改中', '已关闭']

const activeTab = ref<(typeof tabs)[number]['key']>('overview')
const ratingSummary = ref<RatingOverview>({
  items: [],
  tracks: [],
  total: 0,
  pendingRectification: 0,
  blockedAutoClose: 0,
  reusedEvidence: 0,
})
const detailRows = ref<Row[]>([])
const progressRows = ref<Row[]>([])
const detailTotal = ref(0)
const detailKeyword = ref('')
const progressKeyword = ref('')
const progressFilter = ref('')
const errorMessage = ref('')

function resetDetailFilters() {
  detailKeyword.value = ''
  void reload()
}

function resetProgressFilters() {
  progressKeyword.value = ''
  progressFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '防腐记录登记入口尚未接入审批流'
}

function formatValue(value: Row[string]): string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.join('；') : '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

function availableActions(row: Row): string[] {
  const status = String(row['记录状态'] ?? row.status ?? '')
  const progress = String(row['整改进度'] ?? '')
  const actions: string[] = []
  if (status === '待检测') actions.push('开始检测', '标记破损')
  if (status !== '待检测' && progress !== '已关闭') {
    actions.push('提交整改证据', '补充评级依据', '确认修复', '人工核验关闭')
  }
  return actions
}

async function postJson(path: string, body: Record<string, unknown>): Promise<ActionResponse> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error('防腐检测动作未生效，请稍后重试')
  }
  return (await response.json()) as ActionResponse
}

async function runWorkflow(action: string, row: Row) {
  errorMessage.value = ''
  const entryId = String(row.id)
  try {
    let result: ActionResponse

    if (action === '开始检测') {
      result = await postJson(`${ENDPOINT}/${entryId}/actions`, { values: { action } })
    } else if (action === '标记破损') {
      result = await postJson(`${ENDPOINT}/${entryId}/actions`, { values: { action } })
    } else if (action === '提交整改证据') {
      const evidence = window.prompt('请输入整改证据编号、照片编号或复验报告编号', String(row['整改证据'] ?? ''))
      if (evidence === null) return
      result = await postJson(`${ENDPOINT}/${entryId}/rectification/evidence`, {
        values: { 整改证据: evidence },
      })
    } else if (action === '补充评级依据') {
      const basis = window.prompt('请说明评级交界、停用管段或证据复用情况下的最终评级依据', String(row['人工评级依据'] ?? ''))
      if (basis === null) return
      result = await postJson(`${ENDPOINT}/${entryId}/rating/basis`, {
        values: { 评级依据说明: basis },
      })
    } else if (action === '确认修复') {
      const evidence = window.prompt('请输入整改证据编号、照片编号或复验报告编号', String(row['整改证据'] ?? ''))
      if (evidence === null) return
      const basis = window.prompt('如处于评级交界或管段停用，请补充评级依据（可留空但仍不会自动关闭）', String(row['人工评级依据'] ?? ''))
      result = await postJson(`${ENDPOINT}/${entryId}/actions`, {
        values: { action, 整改证据: evidence, 评级依据说明: basis ?? '' },
      })
    } else {
      const note = window.prompt('人工核验关闭必须填写核验说明', '')
      if (note === null) return
      result = await postJson(`${ENDPOINT}/${entryId}/rectification/close`, {
        values: { 核验说明: note },
      })
    }

    if (!result.ok) errorMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '防腐检测操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const detailQuery = new URLSearchParams(detailKeyword.value ? { keyword: detailKeyword.value } : {}).toString()
  const progressParams: Record<string, string> = {}
  if (progressKeyword.value) progressParams.keyword = progressKeyword.value
  if (progressFilter.value) progressParams.progress = progressFilter.value
  const progressQuery = new URLSearchParams(progressParams).toString()

  try {
    const [overviewResponse, detailResponse, progressResponse] = await Promise.all([
      request(`${ENDPOINT}/ratings/overview`),
      request(`${ENDPOINT}?${detailQuery}`),
      request(`${ENDPOINT}/rectifications?${progressQuery}`),
    ])
    if (!overviewResponse.ok || !detailResponse.ok || !progressResponse.ok) {
      throw new Error('防腐检测评级数据读取失败')
    }
    ratingSummary.value = await overviewResponse.json()
    const detailPayload = await detailResponse.json()
    const progressPayload = await progressResponse.json()
    detailRows.value = detailPayload.items ?? []
    detailTotal.value = detailPayload.total ?? detailRows.value.length
    progressRows.value = progressPayload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '防腐检测列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.tab-row { display: flex; gap: 8px; margin: 12px 0; }
.tab-button { border: 1px solid var(--border); background: #fff; border-radius: 6px; padding: 7px 14px; cursor: pointer; }
.tab-button.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.tab-panel h3 { margin: 18px 0 8px; font-size: 15px; }
.filter-wide { flex: 1; min-width: 280px; }
.filter-select { height: 32px; border: 1px solid var(--border); border-radius: 6px; padding: 4px 8px; }
.action-cell { min-width: 220px; flex-wrap: wrap; }
.risk-badge { display: inline-block; color: #b42318; background: #fee4e2; border: 1px solid #fecdca; border-radius: 999px; padding: 2px 8px; font-size: 12px; white-space: nowrap; }
.warn { color: #b42318; }
.link.danger { color: #b42318; }
</style>
