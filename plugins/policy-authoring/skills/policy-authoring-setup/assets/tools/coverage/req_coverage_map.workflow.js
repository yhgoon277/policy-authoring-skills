// ⚠ 유닛당 WORK·NB 2상수 편집 필요 (Workflow args 전달 버그 회피·재검증 전 수동)
export const meta = {
  name: 'hub-req-coverage-map',
  description: 'hub 요구사항 96건을 현재 spec 노드에 매핑 — 8배치 병렬, 결과를 배치별 JSON으로 저장 (①매핑)',
  phases: [{ title: '매핑', detail: '8배치 병렬 요구사항→노드 매핑' }],
}

const UNIT = process.env.COVERAGE_UNIT || 'hub'
const WORK = process.env.COVERAGE_WORK || ('audit/_coverage_work_' + UNIT)
const CATALOG = WORK + '/node_catalog.md'
const BATCHES = WORK + '/batches.json'
const HINTS = WORK + '/stale_hints.json'
const NB = 8

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    decisions: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          requirement_id: { type: 'string' },
          requirement_name: { type: 'string' },
          decision: { type: 'string', enum: ['유지', '통합', '수정', '신설', '삭제(범위밖)'] },
          tobe_nodes: { type: 'array', items: { type: 'string' } },
          asis_source: { type: 'string' },
          rationale: { type: 'string' },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
          catalog_verified: { type: 'boolean' },
        },
        required: ['requirement_id', 'requirement_name', 'decision', 'tobe_nodes', 'asis_source', 'rationale', 'confidence', 'catalog_verified'],
      },
    },
  },
  required: ['decisions'],
}

function buildPrompt(i) {
  return [
    '너는 고객센터 통합허브(hub) 정책서의 요구사항-노드 매핑 분석가다.',
    '',
    '## 먼저 Read할 파일',
    `1. 노드 카탈로그(유일 진실원천): ${CATALOG}`,
    '   - 이 카탈로그에 있는 ID만 존재한다. 여기 없는 ID는 절대 쓰지 마라(환각 금지).',
    `2. 담당 배치: ${BATCHES} 를 Read하고 배열 인덱스 [${i}]의 배치(요구사항 12건)만 담당한다.`,
    `3. stale 후보 힌트(참고만): ${HINTS} — 담당 요구사항 id의 값이 있으면 후보로만 참고하되, 반드시 카탈로그로 재확인하라. 이 힌트는 낡은 데이터라 진실이 아니다.`,
    '',
    '## 각 요구사항(12건)마다 판정',
    '- decision: 유지 / 통합 / 수정 / 신설 / 삭제(범위밖) 중 하나.',
    '  · 현재 spec에 직접 대응 노드가 있으면 유지(여러 as-is를 합친 경우 통합, 변형 반영이면 수정).',
    '  · spec에 새로 만들어 반영했으면 신설. 이 정책서 범위 밖(순수 외부 시스템 구축, 타 모듈 소관 등)이면 삭제(범위밖).',
    '- tobe_nodes: 그 요구를 담고 있는 카탈로그 실존 노드 ID 1개 이상(삭제(범위밖)이면 빈 배열 허용).',
    '  · 화면·흐름 요구 → PR/FN, 정책·기준 요구 → PG/PI. 가장 직접적인 노드 1~4개. 과다 나열 금지.',
    '  · 반드시 카탈로그에 실제로 있는 ID만. 형식 예: PR-CS-HUB-001, FN-CS-HUB-014, PG-CS-ERR-01, PI-CS-REQ-01-06.',
    '- asis_source: as-is 출처를 알면 "서비스›항목"(예: T우주›1:1 문의), 모르면 "-".',
    '- rationale: 왜 이 결정·노드인지 1~2문장.',
    '- confidence: high/medium/low. catalog_verified: tobe_nodes 전부 카탈로그에서 확인했으면 true.',
    "- ⚠️ tobe_nodes·rationale·asis_source·requirement_name 어디에도 '|'(파이프) 문자를 쓰지 마라.",
    '',
    '## 산출 (반드시 둘 다)',
    '(A) 담당 12건 전부를 decisions 배열로 schema 반환.',
    `(B) 동일한 decisions 배열(JSON)을 ${WORK}/map_b${i}.json 파일에 Write하라. 반환값과 완전히 동일해야 한다.`,
  ].join('\n')
}

phase('매핑')
const results = await parallel(
  Array.from({ length: NB }, (_, i) => () =>
    agent(buildPrompt(i), { schema: SCHEMA, label: `map:b${i + 1}`, phase: '매핑' })
  )
)
const all = results.filter(Boolean).flatMap(r => r.decisions || [])
const byDecision = {}
for (const d of all) byDecision[d.decision] = (byDecision[d.decision] || 0) + 1
const notSelfVerified = all.filter(d => !d.catalog_verified).map(d => d.requirement_id)
return {
  batches_returned: results.filter(Boolean).length,
  decisions_returned: all.length,
  byDecision,
  not_self_verified: notSelfVerified,
}
