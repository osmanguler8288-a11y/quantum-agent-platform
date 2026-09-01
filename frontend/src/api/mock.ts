import type { SSEEvent, Atom, ExcitedState, Orbital, PlanStep } from '@/types'

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

// ─── 苯的 3D 坐标（优化后）───
const BENZENE: Atom[] = [
  { symbol: 'C', x: 0.0, y: 1.394, z: 0.0 },
  { symbol: 'C', x: 1.207, y: 0.697, z: 0.0 },
  { symbol: 'C', x: 1.207, y: -0.697, z: 0.0 },
  { symbol: 'C', x: 0.0, y: -1.394, z: 0.0 },
  { symbol: 'C', x: -1.207, y: -0.697, z: 0.0 },
  { symbol: 'C', x: -1.207, y: 0.697, z: 0.0 },
  { symbol: 'H', x: 0.0, y: 2.482, z: 0.0 },
  { symbol: 'H', x: 2.149, y: 1.241, z: 0.0 },
  { symbol: 'H', x: 2.149, y: -1.241, z: 0.0 },
  { symbol: 'H', x: 0.0, y: -2.482, z: 0.0 },
  { symbol: 'H', x: -2.149, y: -1.241, z: 0.0 },
  { symbol: 'H', x: -2.149, y: 1.241, z: 0.0 },
]

// ─── 苯的 HOMO/LUMO 能级（B3LYP/6-31G* 典型值）───
const ORBITALS: Orbital[] = [
  { idx: 19, energy_eV: -11.2, occ: true },
  { idx: 20, energy_eV: -9.1, occ: true },
  { idx: 21, energy_eV: -6.7, occ: true }, // HOMO
  { idx: 22, energy_eV: -0.7, occ: false }, // LUMO
  { idx: 23, energy_eV: 0.6, occ: false },
  { idx: 24, energy_eV: 1.9, occ: false },
]

// ─── TD-DFT 激发态（苯吸收）───
const TD_STATES: ExcitedState[] = [
  { n: 1, energy_eV: 4.86, wavelength_nm: 255, osc_strength: 0.001 },
  { n: 2, energy_eV: 5.60, wavelength_nm: 221, osc_strength: 0.08 },
  { n: 3, energy_eV: 6.20, wavelength_nm: 200, osc_strength: 0.55 },
  { n: 4, energy_eV: 6.89, wavelength_nm: 180, osc_strength: 0.82 },
  { n: 5, energy_eV: 7.10, wavelength_nm: 175, osc_strength: 0.35 },
]

// ─── 红外频率（甲醇示例峰位）───
const IR_FREQS = [1033, 1110, 1345, 1455, 1470, 2830, 2935, 2970, 3340, 3680]
const IR_INTENS = [120, 45, 30, 20, 25, 80, 95, 70, 180, 40]

function planFor(query: string): PlanStep[] {
  const isTddft = /吸收|激发|td|td-?dft/i.test(query)
  const isFreq = /红外|频率|freq/i.test(query)
  const isDipole = /偶极/i.test(query)

  if (isTddft) {
    return [
      { type: 'tool', step: 'build_molecule', action: '从 SMILES 建模苯分子', params: { smiles: 'c1ccccc1' } },
      { type: 'tool', step: 'gen_input', action: '生成 TD-DFT 输入文件', params: { task_type: 'tddft', n_states: 10 } },
      { type: 'tool', step: 'gaussian', action: '运行激发态计算', params: { input_file: 'benzene.gjf' } },
      { type: 'tool', step: 'tddft_analysis', action: '解析激发态结果', params: { output: 'benzene.log' } },
      { type: 'reasoning', step: 'analysis', action: '解读吸收光谱' },
    ]
  }
  if (isFreq) {
    return [
      { type: 'tool', step: 'build_molecule', action: '建模甲醇分子', params: { smiles: 'CO' } },
      { type: 'tool', step: 'gen_input', action: '生成频率计算输入', params: { task_type: 'freq' } },
      { type: 'tool', step: 'gaussian', action: '运行频率计算', params: { input_file: 'methanol.gjf' } },
      { type: 'tool', step: 'freq_analysis', action: '解析振动频率', params: { output: 'methanol.log' } },
      { type: 'reasoning', step: 'analysis', action: '解读红外光谱' },
    ]
  }
  if (isDipole) {
    return [
      { type: 'tool', step: 'build_molecule', action: '建模水分子', params: { smiles: 'O' } },
      { type: 'tool', step: 'gaussian', action: '单点能计算', params: { input_file: 'water.gjf' } },
      { type: 'tool', step: 'dipole', action: '提取偶极矩', params: { out_path: 'water.out' } },
      { type: 'reasoning', step: 'analysis', action: '解读偶极矩' },
    ]
  }
  // 默认：优化 + HOMO/LUMO
  return [
    { type: 'tool', step: 'build_molecule', action: '从 SMILES 建模苯分子', params: { smiles: 'c1ccccc1' } },
    { type: 'tool', step: 'gen_input', action: '生成优化输入文件', params: { task_type: 'opt', method: 'B3LYP', basis: '6-31G*' } },
    { type: 'tool', step: 'gaussian', action: '运行结构优化', params: { input_file: 'benzene.gjf', timeout: 3600 } },
    { type: 'tool', step: 'grep_file', action: '检查是否收敛', params: { path: 'benzene.log', preset: 'convergence' } },
    { type: 'tool', step: 'homo_lumo', action: '提取 HOMO/LUMO 轨道能', params: { fchk_path: 'benzene.fchk' } },
    { type: 'reasoning', step: 'analysis', action: '汇总计算结果并解读' },
  ]
}

/**
 * 生成 mock SSE 事件流。后端联调时替换为 streamWorkflow()。
 */
export async function* mockEventStream(query: string): AsyncGenerator<SSEEvent> {
  const thinking = `我将针对任务「${query}」进行量子化学计算。首先建立分子结构并确定计算方法与基组，然后生成输入文件、运行计算、解析关键数据，最后给出物理解读。`

  // 1. 思考过程（逐字）
  for (const ch of thinking) {
    yield { event: 'thinking_chunk', data: ch }
    await sleep(8)
  }

  // 2. RAG + 记忆（静默）
  yield { event: 'memory_done', data: { count: 3 } }
  await sleep(120)
  yield { event: 'rag_done', data: { context_len: 1024 } }
  await sleep(80)

  // 3. 计划
  const plan = planFor(query)
  yield { event: 'plan_done', data: plan }
  await sleep(300)

  // 4. 逐步执行
  for (let i = 0; i < plan.length; i++) {
    const step = plan[i]
    yield { event: 'step_start', data: { index: i, step } }
    await sleep(400 + Math.random() * 300)

    if (step.type === 'reasoning') {
      yield {
        event: 'step_done',
        data: {
          index: i,
          result: { status: 'success', tool: 'reasoning', result: '分析完成，结果合理。' },
        },
      }
    } else {
      yield {
        event: 'step_done',
        data: {
          index: i,
          result: { status: 'success', tool: step.step, result: `${step.step} 执行成功` },
        },
      }
    }
    await sleep(150)
  }

  // 5. 可视化结果（按场景）
  const isTddft = /吸收|激发|td|td-?dft/i.test(query)
  const isFreq = /红外|频率|freq/i.test(query)
  const isDipole = /偶极/i.test(query)

  if (isTddft) {
    yield { event: 'result_viz', data: { type: 'tddft', states: TD_STATES } }
  } else if (isFreq) {
    yield {
      event: 'result_viz',
      data: {
        type: 'freq',
        n_imag: 0,
        freqs: IR_FREQS,
        intensities: IR_INTENS,
        thermo: { ZPE: '35.2 kcal/mol', H: '38.1 kcal/mol', G: '12.4 kcal/mol' },
      },
    }
  } else if (isDipole) {
    yield { event: 'result_viz', data: { type: 'dipole', components: { x: 0.0, y: 0.0, z: 1.85, tot: 1.85 } } }
  } else {
    yield {
      event: 'result_viz',
      data: {
        type: 'homo_lumo',
        homo_e: -6.7,
        lumo_e: -0.7,
        gap_eV: 6.0,
        orbitals: ORBITALS,
      },
    }
    yield { event: 'result_viz', data: { type: 'structure', atoms: BENZENE } }
  }
  await sleep(200)

  // 6. 评审
  yield {
    event: 'verdict_done',
    data: {
      passed: true,
      reason: '计算正常结束，能量与轨道能级均在物理合理范围内。',
      suggestions: '',
      comment:
        '计算已正常收敛（Normal termination）。HOMO 为 -6.7 eV，LUMO 为 -0.7 eV，能隙 6.0 eV，与苯的典型实验值吻合，说明 B3LYP/6-31G* 对该体系描述可靠。',
    },
  }
  await sleep(200)

  // 7. 完成
  yield { event: 'done', data: { status: 'passed', session_id: 'mock-session-001' } }
}
