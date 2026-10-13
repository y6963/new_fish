<template>
  <div class="workbench-panel">
    <div class="scroll-container">
      <!-- Step 01: Ontology -->
      <div class="step-card" :class="{ 'active': currentPhase === 0, 'completed': currentPhase > 0 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">01</span>
            <span class="step-title">{{ $t('step1.ontologyGeneration') }}</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase > 0" class="badge success">{{ $t('step1.ontologyCompleted') }}</span>
            <span v-else-if="currentPhase === 0" class="badge processing">{{ $t('step1.ontologyGenerating') }}</span>
            <span v-else class="badge pending">{{ $t('step1.ontologyPending') }}</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/graph/ontology/generate</p>
          <p class="description">
            {{ $t('step1.ontologyDesc') }}
          </p>

          <!-- Loading / Progress -->
          <div v-if="currentPhase === 0 && ontologyProgress" class="progress-section">
            <div class="spinner-sm"></div>
            <span>{{ ontologyProgress.message || $t('step1.analyzingDocs') }}</span>
          </div>

          <!-- Detail Overlay -->
          <div v-if="selectedOntologyItem" class="ontology-detail-overlay">
            <div class="detail-header">
               <div class="detail-title-group">
                  <span class="detail-type-badge">{{ selectedOntologyItem.itemType === 'entity' ? 'ENTITY' : 'RELATION' }}</span>
                  <span class="detail-name">{{ selectedOntologyItem.name }}</span>
               </div>
               <button class="close-btn" @click="selectedOntologyItem = null">×</button>
            </div>
            <div class="detail-body">
               <div class="detail-desc">{{ selectedOntologyItem.description }}</div>
               
               <!-- Attributes -->
               <div class="detail-section" v-if="selectedOntologyItem.attributes?.length">
                  <span class="section-label">ATTRIBUTES</span>
                  <div class="attr-list">
                     <div v-for="attr in selectedOntologyItem.attributes" :key="attr.name" class="attr-item">
                        <span class="attr-name">{{ attr.name }}</span>
                        <span class="attr-type">({{ attr.type }})</span>
                        <span class="attr-desc">{{ attr.description }}</span>
                     </div>
                  </div>
               </div>

               <!-- Examples (Entity) -->
               <div class="detail-section" v-if="selectedOntologyItem.examples?.length">
                  <span class="section-label">EXAMPLES</span>
                  <div class="example-list">
                     <span v-for="ex in selectedOntologyItem.examples" :key="ex" class="example-tag">{{ ex }}</span>
                  </div>
               </div>

               <!-- Source/Target (Relation) -->
               <div class="detail-section" v-if="selectedOntologyItem.source_targets?.length">
                  <span class="section-label">CONNECTIONS</span>
                  <div class="conn-list">
                     <div v-for="(conn, idx) in selectedOntologyItem.source_targets" :key="idx" class="conn-item">
                        <span class="conn-node">{{ conn.source }}</span>
                        <span class="conn-arrow">→</span>
                        <span class="conn-node">{{ conn.target }}</span>
                     </div>
                  </div>
               </div>
            </div>
          </div>

          <!-- Generated Entity Tags -->
          <div v-if="projectData?.ontology?.entity_types" class="tags-container" :class="{ 'dimmed': selectedOntologyItem }">
            <span class="tag-label">GENERATED ENTITY TYPES</span>
            <div class="tags-list">
              <span 
                v-for="entity in projectData.ontology.entity_types" 
                :key="entity.name" 
                class="entity-tag clickable"
                @click="selectOntologyItem(entity, 'entity')"
              >
                {{ entity.name }}
              </span>
            </div>
          </div>

          <!-- Generated Relation Tags -->
          <div v-if="projectData?.ontology?.edge_types" class="tags-container" :class="{ 'dimmed': selectedOntologyItem }">
            <span class="tag-label">GENERATED RELATION TYPES</span>
            <div class="tags-list">
              <span 
                v-for="rel in projectData.ontology.edge_types" 
                :key="rel.name" 
                class="entity-tag clickable"
                @click="selectOntologyItem(rel, 'relation')"
              >
                {{ rel.name }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 02: Graph Build -->
      <div class="step-card" :class="{ 'active': currentPhase === 1, 'completed': currentPhase > 1 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">02</span>
            <span class="step-title">{{ $t('step1.graphRagBuild') }}</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase > 1" class="badge success">{{ $t('step1.ontologyCompleted') }}</span>
            <span v-else-if="currentPhase === 1" class="badge processing">{{ buildProgress?.progress || 0 }}%</span>
            <span v-else class="badge pending">{{ $t('step1.ontologyPending') }}</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/graph/build</p>
          <p class="description">
            {{ $t('step1.graphRagDesc') }}
          </p>
          
          <!-- Stats Cards -->
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.nodes }}</span>
              <span class="stat-label">{{ $t('step1.entityNodes') }}</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.edges }}</span>
              <span class="stat-label">{{ $t('step1.relationEdges') }}</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.types }}</span>
              <span class="stat-label">{{ $t('step1.schemaTypes') }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 03: Complete -->
      <div class="step-card" :class="{ 'active': currentPhase === 2, 'completed': currentPhase >= 2 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">03</span>
            <span class="step-title">{{ $t('step1.buildComplete') }}</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase >= 2" class="badge accent">{{ $t('step1.inProgress') }}</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/simulation/create</p>
          <p class="description">{{ $t('step1.buildCompleteDesc') }}</p>
          <button 
            class="action-btn" 
            :disabled="currentPhase < 2 || creatingSimulation"
            @click="handleEnterEnvSetup"
          >
            <span v-if="creatingSimulation" class="spinner-sm"></span>
            {{ creatingSimulation ? $t('step1.creating') : $t('step1.enterEnvSetup') + ' ➝' }}
          </button>
        </div>
      </div>

      <!-- Step 04: Export & Restore -->
      <div class="step-card" :class="{ 'active': showExportPanel }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">04</span>
            <span class="step-title">{{ $t('step1.exportRestore') }}</span>
          </div>
          <div class="step-status">
            <span v-if="exportedFiles.length > 0" class="badge accent">{{ exportedFiles.length }} {{ $t('step1.exported') }}</span>
            <span v-else class="badge pending">{{ $t('step1.notExported') }}</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/graph/export/:id</p>
          <p class="description">{{ $t('step1.exportRestoreDesc') }}</p>
          
          <!-- Export Options -->
          <div class="export-section" v-if="projectData?.graph_id">
            <div class="export-formats">
              <span class="format-label">{{ $t('step1.selectFormat') }}:</span>
              <select v-model="selectedFormat" class="format-select">
                <option value="json">JSON</option>
                <option value="sqlite">SQLite</option>
                <option value="cypher">Cypher (Neo4j)</option>
              </select>
            </div>
            
            <div class="export-actions">
              <button 
                class="action-btn primary" 
                :disabled="exporting || !projectData.graph_id"
                @click="handleExport"
              >
                <span v-if="exporting" class="spinner-sm"></span>
                {{ exporting ? $t('step1.exporting') : $t('step1.exportGraph') }}
              </button>
              
              <button 
                class="action-btn secondary"
                @click="showFileSelector = !showFileSelector"
              >
                {{ $t('step1.loadLocal') }}
              </button>
            </div>
            
            <!-- Export Result -->
            <div v-if="exportResult" class="export-result">
              <div class="result-header">
                <span class="result-title">{{ $t('step1.exportSuccess') }}</span>
                <a :href="exportResult.download_url" class="download-link" target="_blank">
                  {{ $t('step1.download') }}
                </a>
              </div>
              <div class="result-info">
                <span>{{ $t('step1.filename') }}: {{ exportResult.filename }}</span>
                <span>{{ $t('step1.nodeCount') }}: {{ exportResult.graph_info?.node_count }}</span>
                <span>{{ $t('step1.edgeCount') }}: {{ exportResult.graph_info?.edge_count }}</span>
                <span class="checksum">Checksum: {{ exportResult.graph_info?.checksum?.substring(0, 16) }}...</span>
              </div>
            </div>
          </div>
          
          <!-- File Selector for Loading -->
          <div v-if="showFileSelector" class="file-selector">
            <div class="selector-header">
              <span>{{ $t('step1.localFiles') }}</span>
              <button class="close-btn" @click="showFileSelector = false">×</button>
            </div>
            
            <div class="file-list" v-if="exportedFiles.length > 0">
              <div 
                v-for="file in exportedFiles" 
                :key="file.filename"
                class="file-item"
              >
                <div class="file-info">
                  <span class="file-name">{{ file.filename }}</span>
                  <span class="file-meta">{{ formatFileSize(file.size) }} | {{ file.format }}</span>
                </div>
                <div class="file-actions">
                  <button class="mini-btn" @click="loadLocalGraph(file.filename)">
                    {{ $t('step1.load') }}
                  </button>
                  <a :href="`/api/graph/download/${file.filename}`" class="mini-btn" target="_blank">
                    {{ $t('step1.download') }}
                  </a>
                </div>
              </div>
            </div>
            <div v-else class="no-files">
              {{ $t('step1.noLocalFiles') }}
            </div>
          </div>
          
          <!-- Validation Result -->
          <div v-if="validationResult" class="validation-result" :class="{ valid: validationResult.is_valid, invalid: !validationResult.is_valid }">
            <div class="validation-header">
              <span class="validation-icon">{{ validationResult.is_valid ? '✓' : '✗' }}</span>
              <span class="validation-title">{{ validationResult.is_valid ? $t('step1.validationPass') : $t('step1.validationFail') }}</span>
            </div>
            <div v-if="validationResult.checksum" class="validation-details">
              <span>{{ $t('step1.checksumMatch') }}: {{ validationResult.checksum.match ? $t('step1.yes') : $t('step1.no') }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SYSTEM DASHBOARD</span>
        <span class="log-id">{{ projectData?.project_id || 'NO_PROJECT' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { createSimulation } from '../api/simulation'
import { exportGraph, listExports, getLocalGraphData, validateLocalGraph } from '../api/graph'

const router = useRouter()
const { t } = useI18n()

const props = defineProps({
  currentPhase: { type: Number, default: 0 },
  projectData: Object,
  ontologyProgress: Object,
  buildProgress: Object,
  graphData: Object,
  systemLogs: { type: Array, default: () => [] },
  onGraphDataChange: Function  // 用于通知父组件图谱数据变化
})

defineEmits(['next-step'])

const selectedOntologyItem = ref(null)
const logContent = ref(null)
const creatingSimulation = ref(false)

// Export & Restore State
const selectedFormat = ref('json')
const exporting = ref(false)
const exportResult = ref(null)
const exportedFiles = ref([])
const showFileSelector = ref(false)
const validationResult = ref(null)

// Computed: 是否显示导出面板
const showExportPanel = computed(() => {
  return props.projectData?.graph_id && props.currentPhase >= 2
})

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 导出图谱
const handleExport = async () => {
  if (!props.projectData?.graph_id) {
    alert('No graph to export')
    return
  }
  
  exporting.value = true
  exportResult.value = null
  validationResult.value = null
  
  try {
    const res = await exportGraph(props.projectData.graph_id, selectedFormat.value)
    
    if (res.success) {
      exportResult.value = res.data
      // 刷新文件列表
      await loadExportedFiles()
      // 验证导出
      await verifyExport(res.data.filename)
    } else {
      alert('Export failed: ' + res.error)
    }
  } catch (err) {
    console.error('Export error:', err)
    alert('Export error: ' + err.message)
  } finally {
    exporting.value = false
  }
}

// 加载已导出的文件列表
const loadExportedFiles = async () => {
  try {
    const res = await listExports()
    if (res.success) {
      exportedFiles.value = res.data || []
    }
  } catch (err) {
    console.error('Load exports error:', err)
  }
}

// 加载本地图谱
const loadLocalGraph = async (filename) => {
  try {
    const res = await getLocalGraphData(filename)
    
    if (res.success && res.data) {
      // 将本地图谱数据传递给父组件
      if (props.onGraphDataChange) {
        props.onGraphDataChange(res.data)
      }
      // 验证图谱
      await verifyExport(filename)
      showFileSelector.value = false
    } else {
      alert('Failed to load local graph: ' + res.error)
    }
  } catch (err) {
    console.error('Load local graph error:', err)
    alert('Load error: ' + err.message)
  }
}

// 验证导出文件
const verifyExport = async (filename) => {
  try {
    const res = await validateLocalGraph(filename)
    if (res.success) {
      validationResult.value = res.data
    }
  } catch (err) {
    console.error('Validation error:', err)
  }
}

// 初始化时加载导出文件列表
watch(showExportPanel, (newVal) => {
  if (newVal) {
    loadExportedFiles()
  }
}, { immediate: true })

// 进入环境搭建 - 创建 simulation 并跳转
const handleEnterEnvSetup = async () => {
  if (!props.projectData?.project_id || !props.projectData?.graph_id) {
    console.error('缺少项目或图谱信息')
    return
  }
  
  creatingSimulation.value = true
  
  try {
    const res = await createSimulation({
      project_id: props.projectData.project_id,
      graph_id: props.projectData.graph_id,
      enable_twitter: true,
      enable_reddit: true
    })
    
    if (res.success && res.data?.simulation_id) {
      // 跳转到 simulation 页面
      router.push({
        name: 'Simulation',
        params: { simulationId: res.data.simulation_id }
      })
    } else {
      console.error('创建模拟失败:', res.error)
      alert(t('step1.createSimulationFailed', { error: res.error || t('common.unknownError') }))
    }
  } catch (err) {
    console.error('创建模拟异常:', err)
    alert(t('step1.createSimulationException', { error: err.message }))
  } finally {
    creatingSimulation.value = false
  }
}

const selectOntologyItem = (item, type) => {
  selectedOntologyItem.value = { ...item, itemType: type }
}

const graphStats = computed(() => {
  const nodes = props.graphData?.node_count || props.graphData?.nodes?.length || 0
  const edges = props.graphData?.edge_count || props.graphData?.edges?.length || 0
  const types = props.projectData?.ontology?.entity_types?.length || 0
  return { nodes, edges, types }
})

const formatDate = (dateStr) => {
  if (!dateStr) return '--:--:--'
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour12: false }) + '.' + d.getMilliseconds()
}

// Auto-scroll logs
watch(() => props.systemLogs.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})
</script>

<style scoped>
.workbench-panel {
  height: 100%;
  background-color: #FAFAFA;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.scroll-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.step-card {
  background: #FFF;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  border: 1px solid #EAEAEA;
  transition: all 0.3s ease;
  position: relative; /* For absolute overlay */
}

.step-card.active {
  border-color: #FF5722;
  box-shadow: 0 4px 12px rgba(255, 87, 34, 0.08);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.step-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  font-weight: 700;
  color: #E0E0E0;
}

.step-card.active .step-num,
.step-card.completed .step-num {
  color: #000;
}

.step-title {
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.5px;
}

.badge {
  font-size: 10px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.success { background: #E8F5E9; color: #2E7D32; }
.badge.processing { background: #FF5722; color: #FFF; }
.badge.accent { background: #FF5722; color: #FFF; }
.badge.pending { background: #F5F5F5; color: #999; }

.api-note {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
  margin-bottom: 8px;
}

.description {
  font-size: 12px;
  color: #666;
  line-height: 1.5;
  margin-bottom: 16px;
}

/* Step 01 Tags */
.tags-container {
  margin-top: 12px;
  transition: opacity 0.3s;
}

.tags-container.dimmed {
    opacity: 0.3;
    pointer-events: none;
}

.tag-label {
  display: block;
  font-size: 10px;
  color: #AAA;
  margin-bottom: 8px;
  font-weight: 600;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-tag {
  background: #F5F5F5;
  border: 1px solid #EEE;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  color: #333;
  font-family: 'JetBrains Mono', monospace;
  transition: all 0.2s;
}

.entity-tag.clickable {
    cursor: pointer;
}

.entity-tag.clickable:hover {
    background: #E0E0E0;
    border-color: #CCC;
}

/* Ontology Detail Overlay */
.ontology-detail-overlay {
    position: absolute;
    top: 60px; /* Below header roughly */
    left: 20px;
    right: 20px;
    bottom: 20px;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(4px);
    z-index: 10;
    border: 1px solid #EAEAEA;
    box-shadow: 0 4px 20px rgba(0,0,0,0.05);
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

.detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid #EAEAEA;
    background: #FAFAFA;
}

.detail-title-group {
    display: flex;
    align-items: center;
    gap: 8px;
}

.detail-type-badge {
    font-size: 9px;
    font-weight: 700;
    color: #FFF;
    background: #000;
    padding: 2px 6px;
    border-radius: 2px;
    text-transform: uppercase;
}

.detail-name {
    font-size: 14px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}

.close-btn {
    background: none;
    border: none;
    font-size: 18px;
    color: #999;
    cursor: pointer;
    line-height: 1;
}

.close-btn:hover {
    color: #333;
}

.detail-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
}

.detail-desc {
    font-size: 12px;
    color: #444;
    line-height: 1.5;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px dashed #EAEAEA;
}

.detail-section {
    margin-bottom: 16px;
}

.section-label {
    display: block;
    font-size: 10px;
    font-weight: 600;
    color: #AAA;
    margin-bottom: 8px;
}

.attr-list, .conn-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.attr-item {
    font-size: 11px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: baseline;
    padding: 4px;
    background: #F9F9F9;
    border-radius: 4px;
}

.attr-name {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    color: #000;
}

.attr-type {
    color: #999;
    font-size: 10px;
}

.attr-desc {
    color: #555;
    flex: 1;
    min-width: 150px;
}

.example-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.example-tag {
    font-size: 11px;
    background: #FFF;
    border: 1px solid #E0E0E0;
    padding: 3px 8px;
    border-radius: 12px;
    color: #555;
}

.conn-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    padding: 6px;
    background: #F5F5F5;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
}

.conn-node {
    font-weight: 600;
    color: #333;
}

.conn-arrow {
    color: #BBB;
}

/* Step 02 Stats */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  background: #F9F9F9;
  padding: 16px;
  border-radius: 6px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #000;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 9px;
  color: #999;
  text-transform: uppercase;
  margin-top: 4px;
  display: block;
}

/* Step 03 Button */
.action-btn {
  width: 100%;
  background: #000;
  color: #FFF;
  border: none;
  padding: 14px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.action-btn:hover:not(:disabled) {
  opacity: 0.8;
}

.action-btn:disabled {
  background: #CCC;
  cursor: not-allowed;
}

.progress-section {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #FF5722;
  margin-bottom: 12px;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid #FFCCBC;
  border-top-color: #FF5722;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* System Logs */
.system-logs {
  background: #000;
  color: #DDD;
  padding: 16px;
  font-family: 'JetBrains Mono', monospace;
  border-top: 1px solid #222;
  flex-shrink: 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #333;
  padding-bottom: 8px;
  margin-bottom: 8px;
  font-size: 10px;
  color: #888;
}

.log-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 80px; /* Approx 4 lines visible */
  overflow-y: auto;
  padding-right: 4px;
}

.log-content::-webkit-scrollbar {
  width: 4px;
}

.log-content::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 2px;
}

.log-line {
  font-size: 11px;
  display: flex;
  gap: 12px;
  line-height: 1.5;
}

.log-time {
  color: #666;
  min-width: 75px;
}

.log-msg {
  color: #CCC;
  word-break: break-all;
}

/* Export Section */
.export-section {
  margin-top: 16px;
}

.export-formats {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.format-label {
  font-size: 12px;
  color: #666;
}

.format-select {
  padding: 6px 12px;
  border: 1px solid #E0E0E0;
  border-radius: 4px;
  background: white;
  font-size: 12px;
  cursor: pointer;
}

.export-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.action-btn {
  padding: 10px 20px;
  background: #FF5722;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: background 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn:hover:not(:disabled) {
  background: #E64A19;
}

.action-btn:disabled {
  background: #CCC;
  cursor: not-allowed;
}

.action-btn.primary {
  background: #7B2D8E;
}

.action-btn.primary:hover:not(:disabled) {
  background: #5A1F6B;
}

.action-btn.secondary {
  background: #666;
}

.action-btn.secondary:hover:not(:disabled) {
  background: #555;
}

.export-result {
  background: #E8F5E9;
  border: 1px solid #A5D6A7;
  border-radius: 6px;
  padding: 12px;
  margin-top: 12px;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.result-title {
  font-weight: 600;
  color: #2E7D32;
}

.download-link {
  color: #1976D2;
  text-decoration: none;
  font-size: 12px;
}

.download-link:hover {
  text-decoration: underline;
}

.result-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: #555;
}

.result-info .checksum {
  font-family: 'JetBrains Mono', monospace;
  color: #888;
}

/* File Selector */
.file-selector {
  background: #F5F5F5;
  border: 1px solid #E0E0E0;
  border-radius: 6px;
  margin-top: 12px;
  overflow: hidden;
}

.selector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: #EEE;
  font-size: 12px;
  font-weight: 600;
}

.file-list {
  max-height: 200px;
  overflow-y: auto;
}

.file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid #E0E0E0;
}

.file-item:last-child {
  border-bottom: none;
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  font-size: 12px;
  font-weight: 500;
  color: #333;
}

.file-meta {
  font-size: 10px;
  color: #888;
}

.file-actions {
  display: flex;
  gap: 6px;
}

.mini-btn {
  padding: 4px 10px;
  background: #FFF;
  border: 1px solid #DDD;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  color: #333;
  text-decoration: none;
  display: inline-block;
}

.mini-btn:hover {
  background: #F0F0F0;
}

.no-files {
  padding: 20px;
  text-align: center;
  color: #999;
  font-size: 12px;
}

/* Validation Result */
.validation-result {
  margin-top: 12px;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
}

.validation-result.valid {
  background: #E8F5E9;
  border: 1px solid #A5D6A7;
}

.validation-result.invalid {
  background: #FFEBEE;
  border: 1px solid #EF9A9A;
}

.validation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.validation-icon {
  font-size: 16px;
  font-weight: bold;
}

.validation-result.valid .validation-icon {
  color: #2E7D32;
}

.validation-result.invalid .validation-icon {
  color: #C62828;
}

.validation-title {
  font-weight: 600;
}

.validation-details {
  font-size: 11px;
  color: #555;
}

/* Close button */
.close-btn {
  background: none;
  border: none;
  font-size: 18px;
  color: #999;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: #333;
}
</style>
