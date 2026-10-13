import service from './index'

/**
 * 生成本体（上传文档和模拟需求）
 * @param {Object} data - 包含files, simulation_requirement, project_name等
 * @returns {Promise}
 */
export function generateOntology(formData) {
  return service({
    url: '/api/graph/ontology/generate',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

/**
 * 构建图谱
 * @param {Object} data - 包含project_id, graph_name等
 * @returns {Promise}
 */
export function buildGraph(data) {
  return service({
    url: '/api/graph/build',
    method: 'post',
    data
  })
}

/**
 * 查询任务状态
 * @param {String} taskId - 任务ID
 * @returns {Promise}
 */
export function getTaskStatus(taskId) {
  return service({
    url: `/api/graph/task/${taskId}`,
    method: 'get'
  })
}

/**
 * 获取图谱数据
 * @param {String} graphId - 图谱ID
 * @returns {Promise}
 */
export function getGraphData(graphId) {
  return service({
    url: `/api/graph/data/${graphId}`,
    method: 'get'
  })
}

/**
 * 获取项目信息
 * @param {String} projectId - 项目ID
 * @returns {Promise}
 */
export function getProject(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}

/**
 * 导出图谱
 * @param {String} graphId - 图谱ID
 * @param {String} format - 导出格式: 'json' | 'sqlite' | 'cypher'
 * @returns {Promise}
 */
export function exportGraph(graphId, format = 'json') {
  return service({
    url: `/api/graph/export/${graphId}`,
    method: 'post',
    data: { format }
  })
}

/**
 * 列出所有导出文件
 * @returns {Promise}
 */
export function listExports() {
  return service({
    url: '/api/graph/export/list',
    method: 'get'
  })
}

/**
 * 获取本地导出的图谱数据
 * @param {String} filename - 导出文件名
 * @returns {Promise}
 */
export function getLocalGraphData(filename) {
  return service({
    url: `/api/graph/local/${filename}`,
    method: 'get'
  })
}

/**
 * 验证本地图谱文件
 * @param {String} filename - 导出文件名
 * @returns {Promise}
 */
export function validateLocalGraph(filename) {
  return service({
    url: `/api/graph/validate/${filename}`,
    method: 'get'
  })
}

/**
 * 验证导出文件与原始图谱的一致性
 * @param {String} graphId - Zep 图谱ID
 * @param {String} exportFilename - 导出文件名
 * @returns {Promise}
 */
export function verifyGraphExport(graphId, exportFilename) {
  return service({
    url: `/api/graph/verify/${graphId}`,
    method: 'post',
    data: { export_filename: exportFilename }
  })
}

/**
 * 下载导出的图谱文件
 * @param {String} filename - 导出文件名
 * @returns {string} 下载URL
 */
export function getExportDownloadUrl(filename) {
  return `/api/graph/download/${filename}`
}
