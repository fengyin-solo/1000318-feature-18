<template>
  <section class="page" data-module="corrosion">
    <header class="page-head">
      <div>
        <h2>防腐检测评级整改跟踪</h2>
        <p class="page-desc">连接防腐记录、检测管段、防腐层类型与破损点数量；评级总览、检测详情和整改进度始终读取同一次判定。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记防腐记录</button>
        <button class="btn" type="button" @click="exportRows">导出防腐检测清单</button>
      </div>
    </header>

    <div class="stat-row rating-stats">
      <article v-for="item in overviewCards" :key="item.label" class="stat-card" :class="{ warning: item.value > 0 && item.label.includes('禁止') }">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>记录编号 / 检测管段</span>
        <input v-model="keyword" placeholder="按 CORR 或 PIPE 编号检索" />
      </label>
      <label class="filter-item">
        <span>整改状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <section class="panel">
      <div class="panel-head">
        <h3>评级总览（同一次判定）</h3>
        <span class="judgement-hint">判定编号贯穿总览、检测详情与整改进度</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>判定编号</th>
            <th>防腐记录</th>
            <th>检测管段</th>
            <th>管段状态</th>
            <th>防腐层类型</th>
            <th>破损点数量</th>
            <th>防腐等级</th>
            <th>整改状态</th>
            <th>风险标记 / 禁止自动关闭依据</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredOverview" :key="String(row.id ?? row['记录编号'])" :class="{ locked: row['禁止自动关闭'] }">
            <td><strong>{{ row['判定编号'] }}</strong></td>
            <td>{{ row['记录编号'] }}</td>
            <td>{{ row['检测管段'] }}</td>
            <td>{{ row['管段状态'] }}</td>
            <td>{{ row['防腐层类型'] }}</td>
            <td>{{ row['破损点数量'] }}</td>
            <td><span class="level-badge" :class="levelClass(String(row['防腐等级']))">{{ row['防腐等级'] }}</span></td>
            <td>{{ row['状态'] }}</td>
            <td class="risk-cell">
              <div class="tag-list">
                <span v-for="flag in (row['风险标记'] as string[])" :key="flag" class="risk-tag">{{ flag }}</span>
                <span v-if="!(row['风险标记'] as string[])?.length" class="muted-text">无</span>
              </div>
              <small v-if="row['自动关闭拦截原因']" class="risk-reason">{{ row['自动关闭拦截原因'] }}</small>
            </td>
            <td class="row-actions compact">
              <button class="link" type="button" @click="showDetail(Number(row.id ?? 0))">检测详情</button>
              <button class="link" type="button" @click="showProgress(Number(row.id ?? 0))">整改进度</button>
              <button
                v-for="action in availableActions(String(row['状态']))"
                :key="action.name"
                class="link"
                :class="{ danger: action.warning }"
                type="button"
                @click="openAction(action, row)"
              >
                {{ action.name }}
              </button>
            </td>
          </tr>
          <tr v-if="!filteredOverview.length">
            <td colspan="10" class="empty-state">暂无符合条件的防腐评级记录</td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="selectedDetail" class="detail-grid">
      <section class="panel detail-panel">
        <div class="panel-head">
          <h3>检测详情</h3>
          <button class="btn ghost small" type="button" @click="closePanels">关闭</button>
        </div>
        <div class="judgement-strip">
          <span>同一次判定</span>
          <strong>{{ selectedDetail['判定编号'] }}</strong>
        </div>
        <dl class="detail-list">
          <template v-for="item in detailFields" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd>{{ item.value || '—' }}</dd>
          </template>
          <dt>风险标记</dt>
          <dd>
            <span v-for="flag in selectedDetail['风险标记']" :key="flag" class="risk-tag">{{ flag }}</span>
            <span v-if="!selectedDetail['风险标记'].length" class="muted-text">无</span>
          </dd>
          <dt>自动关闭</dt>
          <dd :class="{ 'risk-text': selectedDetail['禁止自动关闭'] }">
            {{ selectedDetail['禁止自动关闭'] ? `禁止：${selectedDetail['自动关闭拦截原因']}` : '允许按规则自动关闭' }}
          </dd>
        </dl>
      </section>

      <section v-if="selectedProgress && String(selectedProgress.id) === String(selectedDetail.id)" class="panel detail-panel">
        <div class="panel-head">
          <h3>整改进度</h3>
          <span class="judgement-pill">{{ selectedProgress['判定编号'] }}</span>
        </div>
        <div class="progress-summary">
          <strong>{{ selectedProgress['当前节点'] }}</strong>
          <span>{{ selectedProgress['进度百分比'] }}%</span>
        </div>
        <div class="progress-track"><span :style="{ width: `${selectedProgress['进度百分比']}%` }" /></div>
        <ol class="progress-steps">
          <li v-for="step in selectedProgress.steps" :key="step['节点']" :class="{ done: step['完成'] }">
            <strong>{{ step['节点'] }}</strong>
            <span>{{ step['说明'] }}</span>
          </li>
        </ol>
        <p v-if="selectedProgress['证据复用']" class="risk-text">{{ selectedProgress['证据复用说明'] }}</p>
      </section>
    </div>

    <div v-if="activeDialog" class="modal-backdrop" @click.self="closeDialog">
      <form class="modal-card" @submit.prevent="submitDialog">
        <h3>{{ activeDialog.title }}</h3>
        <p class="muted-text">{{ activeDialog.description }}</p>

        <template v-if="activeDialog.type === 'create'">
          <label v-for="field in createFields" :key="field.name" class="form-item">
            <span>{{ field.label }}{{ field.required ? ' *' : '' }}</span>
            <input v-model="dialogForm[field.name]" :type="field.type ?? 'text'" />
          </label>
        </template>

        <template v-else>
          <div class="dialog-judgement">
            <span>当前判定</span>
            <strong>{{ activeDialog.row['判定编号'] }}</strong>
            <span class="level-badge" :class="levelClass(String(activeDialog.row['防腐等级']))">{{ activeDialog.row['防腐等级'] }}</span>
          </div>
          <label v-if="activeDialog.type === 'rating'" class="form-item">
            <span>评级依据 {{ needsRatingBasis(activeDialog.row) ? '*' : '' }}</span>
            <textarea v-model="dialogForm['评级依据']" :placeholder="ratingBasisPlaceholder(activeDialog.row)" rows="4" />
            <small v-if="needsRatingBasis(activeDialog.row)" class="risk-text">交界点或停用管段必须说明人工依据，否则系统禁止评级关闭。</small>
          </label>
          <template v-if="activeDialog.type === 'evidence'">
            <label class="form-item">
              <span>整改证据编号 *</span>
              <input v-model="dialogForm['整改证据编号']" placeholder="如 EVID-0102" />
            </label>
            <label class="form-item">
              <span>证据复用依据</span>
              <textarea v-model="dialogForm['证据复用依据']" rows="3" placeholder="若证据编号已被其他记录使用，必须说明为何可复用" />
            </label>
          </template>
          <label v-if="activeDialog.type === 'close'" class="form-item">
            <span>人工关闭复核依据 {{ activeDialog.row['禁止自动关闭'] ? '*' : '' }}</span>
            <textarea v-model="dialogForm['关闭依据']" rows="3" placeholder="说明复核结论、停用处置或重复证据核验情况" />
          </label>
        </template>

        <footer class="dialog-actions">
          <button class="btn ghost" type="button" @click="closeDialog">取消</button>
          <button class="btn primary" type="submit">确认提交</button>
        </footer>
        <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条防腐检测记录</span>
      <span v-if="consistencyError" class="error-text">{{ consistencyError }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Primitive = string | number | boolean | null | undefined
type Row = Record<string, Primitive>
type Detail = Row & {
  '判定编号': string
  '风险标记': string[]
  '检测管段': Record<string, Primitive>
  '防腐记录': Record<string, Primitive>
}
type OverviewItem = Row & { id?: number; '判定编号': string; '风险标记': string[]; '状态': string }
type Progress = Row & {
  id: number
  '判定编号': string
  '进度百分比': number
  '当前节点': string
  steps: { 节点: string; 说明: string; 完成: boolean }[]
}
type DialogType = 'create' | 'rating' | 'evidence' | 'close' | 'simple'
type ActionDefinition = {
  name: string
  type: DialogType
  action?: string
  warning?: boolean
  statuses: string[]
  description: string
}

const ENDPOINT = '/api/corrosion'
const statuses = ['待检测', '已检测', '待整改', '整改中', '待复核', '已关闭']
const actionDefinitions: ActionDefinition[] = [
  { name: '开始检测', type: 'simple', action: '开始检测', statuses: ['待检测'], description: '采集管地电位、破损点数量和防腐层检测数据。' },
  { name: '提交评级', type: 'rating', action: '提交评级', warning: true, statuses: ['已检测', '待整改', '整改中'], description: '依据破损点数量、防腐层类型和管段状态固化一次评级判定。' },
  { name: '标记破损', type: 'simple', action: '标记破损', statuses: ['已检测'], description: '评级为 III/IV 级或发现破损时进入待整改。' },
  { name: '提交整改', type: 'simple', action: '提交整改', statuses: ['待整改'], description: '整改单位开始处理防腐层破损点。' },
  { name: '提交证据', type: 'evidence', action: '提交证据', warning: true, statuses: ['整改中', '待复核'], description: '上传整改证据；证据重复使用时必须说明复用依据，且禁止自动关闭。' },
  { name: '人工关闭', type: 'close', action: '人工关闭', warning: true, statuses: ['待复核'], description: '对禁止自动关闭的判定进行人工复核并归档。' },
]
const createFields = [
  { name: '记录编号', label: '防腐记录编号', required: true },
  { name: '检测管段', label: '检测管段编号', required: true },
  { name: '防腐层类型', label: '防腐层类型', required: true },
  { name: '破损点数量', label: '破损点数量', type: 'number', required: true },
  { name: '管地电位', label: '管地电位' },
  { name: '检测日期', label: '检测日期' },
  { name: '检测人员', label: '检测人员' },
]

const keyword = ref('')
const statusFilter = ref('')
const rows = ref<OverviewItem[]>([])
const total = ref(0)
const errorMessage = ref('')
const consistencyError = ref('')
const selectedDetail = ref<Detail | null>(null)
const selectedProgress = ref<Progress | null>(null)
const activeDialog = ref<{ type: DialogType; title: string; description: string; row: OverviewItem; action?: string } | null>(null)
const dialogForm = reactive<Record<string, string>>({})

const overviewCards = ref<{ label: string; value: number }[]>([])
const filteredOverview = computed(() => rows.value)
const detailFields = computed(() => {
  const detail = selectedDetail.value
  if (!detail) return []
  const pipe = detail['检测管段'] as Record<string, Primitive>
  const record = detail['防腐记录'] as Record<string, Primitive>
  return [
    { label: '记录编号', value: record['记录编号'] },
    { label: '检测管段', value: pipe['管段编号'] },
    { label: '管段状态', value: pipe['管段状态'] },
    { label: '管线类型 / 道路', value: `${pipe['管线类型'] ?? ''} / ${pipe['所在道路'] ?? ''}` },
    { label: '防腐层类型', value: detail['防腐层类型'] },
    { label: '破损点数量', value: record['破损点数量'] },
    { label: '管地电位', value: record['管地电位'] },
    { label: '检测日期 / 人员', value: `${record['检测日期'] ?? ''} / ${record['检测人员'] ?? ''}` },
    { label: '防腐等级', value: detail['防腐等级'] },
    { label: '评级依据', value: detail['评级依据'] },
  ]
})

function availableActions(status: string): ActionDefinition[] {
  return actionDefinitions.filter(item => item.statuses.includes(status))
}

function levelClass(level: string) {
  return {
    'level-1': level === 'I级',
    'level-2': level === 'II级',
    'level-3': level === 'III级',
    'level-4': level === 'IV级',
  }
}

function needsRatingBasis(row: OverviewItem) {
  const count = Number(row['破损点数量'])
  const boundary = [5, 15, 30].includes(count)
  const stopped = row['管段状态'] === '停用'
  return boundary || stopped
}

function ratingBasisPlaceholder(row: OverviewItem) {
  const reasons: string[] = []
  if ([5, 15, 30].includes(Number(row['破损点数量']))) reasons.push('点数处于评级交界')
  if (row['管段状态'] === '停用') reasons.push('管段已停用')
  return reasons.length ? `${reasons.join('、')}，请写明按较高风险或停用处置的依据` : '可补充检测班组判定依据'
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  Object.keys(dialogForm).forEach(key => delete dialogForm[key])
  activeDialog.value = {
    type: 'create',
    title: '登记防腐记录',
    description: '检测管段需与管段档案编号一致，评级时会自动关联管段状态。',
    row: {} as OverviewItem,
  }
}

function openAction(definition: ActionDefinition, row: OverviewItem) {
  Object.keys(dialogForm).forEach(key => delete dialogForm[key])
  if (definition.type === 'evidence' && row['整改证据编号']) {
    dialogForm['整改证据编号'] = String(row['整改证据编号'])
  }
  activeDialog.value = {
    type: definition.type,
    title: definition.name,
    description: definition.description,
    row,
    action: definition.action,
  }
}

function closeDialog() {
  activeDialog.value = null
  errorMessage.value = ''
}

async function submitDialog() {
  if (!activeDialog.value) return
  errorMessage.value = ''
  if (activeDialog.value.type === 'create') {
    await submitCreate()
  } else {
    await submitAction(activeDialog.value.row)
  }
}

async function submitCreate() {
  const values: Record<string, Primitive> = { ...dialogForm }
  if (values['破损点数量'] !== undefined) values['破损点数量'] = Number(values['破损点数量'])
  const response = await request(ENDPOINT, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  const payload = await response.json()
  if (!response.ok || !payload.ok) {
    errorMessage.value = payload.message || payload.detail || '防腐记录登记失败'
    return
  }
  closeDialog()
  await reload()
}

async function submitAction(row: OverviewItem) {
  if (!activeDialog?.value?.action) return
  const values: Record<string, Primitive> = { action: activeDialog.value.action, ...dialogForm }
  const response = await request(`${ENDPOINT}/${row.id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  const payload = await response.json()
  if (!response.ok || !payload.ok) {
    errorMessage.value = payload.message || payload.detail || '操作未生效'
    return
  }
  closeDialog()
  await reload()
  if (selectedDetail.value) await showDetail(Number(selectedDetail.value.id ?? selectedDetail.value['防腐记录']?.id))
}

function closePanels() {
  selectedDetail.value = null
  selectedProgress.value = null
  consistencyError.value = ''
}

async function showDetail(id: number) {
  consistencyError.value = ''
  if (!id) return
  try {
    const [detail, progress] = await Promise.all([
      fetchJson<Detail>(`${ENDPOINT}/${id}/detection`),
      fetchJson<Progress>(`${ENDPOINT}/${id}/progress`),
    ])
    if (detail['判定编号'] !== progress['判定编号']) {
      consistencyError.value = `检测详情与整改进度判定不一致：${detail['判定编号']} / ${progress['判定编号']}`
    }
    selectedDetail.value = detail
    selectedProgress.value = progress
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测详情读取失败'
  }
}

async function showProgress(id: number) {
  await showDetail(id)
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) throw new Error(`接口返回 ${response.status}，数据未更新`)
  return (await response.json()) as T
}

async function reload() {
  errorMessage.value = ''
  const retainedDetailId = selectedDetail.value ? Number(selectedDetail.value.id) : null
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('防腐记录列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length

    const overview = await fetchJson<{ cards: { label: string; value: number }[] }>(`${ENDPOINT}/rating/overview`)
    overviewCards.value = overview.cards
    if (retainedDetailId !== null) await showDetail(retainedDetailId)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '防腐检测列表读取失败'
  }
}

onMounted(reload)
</script>
