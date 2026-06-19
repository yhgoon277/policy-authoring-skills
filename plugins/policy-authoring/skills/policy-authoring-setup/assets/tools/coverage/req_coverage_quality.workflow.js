// ⚠ 유닛당 WORK·NB 2상수 편집 필요 (Workflow args 전달 버그 회피·재검증 전 수동)
export const meta = {
  name: 'hub-req-coverage-quality',
  description: 'hub 96건 ②반영 품질 4등급 + 적대검증 (QA→ADV pipeline, 배치별 결과 저장)',
  phases: [
    { title: '품질평가', detail: '8배치 4등급 1차 판정' },
    { title: '적대검증', detail: '충실 반영 표적 회의적 재검증' },
  ],
}
const UNIT = process.env.COVERAGE_UNIT || 'hub'
const WORK = process.env.COVERAGE_WORK || ('audit/_coverage_work_' + UNIT)
const NB = 8
const GRADES = ['충실 반영', '부분 반영', '이름만 반영', '미반영', '범위밖']

const QA_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { grades: { type: 'array', items: {
    type: 'object', additionalProperties: false,
    properties: {
      requirement_id: { type: 'string' },
      grade: { type: 'string', enum: GRADES },
      representative_node: { type: 'string' },
      evidence: { type: 'string' },
      gap: { type: 'string' },
      proposed_backlog: { type: 'string' },
    },
    required: ['requirement_id', 'grade', 'representative_node', 'evidence', 'gap', 'proposed_backlog'],
  } } },
  required: ['grades'],
}
const ADV_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { reviews: { type: 'array', items: {
    type: 'object', additionalProperties: false,
    properties: {
      requirement_id: { type: 'string' },
      original_grade: { type: 'string' },
      challenge: { type: 'string', enum: ['동의', '강등 제안', '승급 제안'] },
      revised_grade: { type: 'string' },
      counter_evidence: { type: 'string' },
    },
    required: ['requirement_id', 'original_grade', 'challenge', 'revised_grade', 'counter_evidence'],
  } } },
  required: ['reviews'],
}

function qaPrompt(i) {
  return [
    '너는 고객센터 통합허브(hub) 정책서의 요구사항 반영 품질 평가자다.',
    `## Read: ${WORK}/qa_input_b${i}.json — 담당 요구사항 12건.`,
    '각 항목 필드: requirement_id, name, description(요구 원문), decision(매핑 결정), tobe_nodes(매핑 노드), node_bodies(그 노드의 실제 정책 본문 — PI는 rule/criteria/notice/tables, FN은 desc/details).',
    '',
    '## 각 요구사항을 4등급으로 판정 (node_bodies의 실제 본문을 근거로)',
    '- 충실 반영: 매핑 노드 본문(특히 PI rule_statement/criteria/notice)이 요구의 핵심 조건을 직접·구체적으로 명시.',
    '- 부분 반영: 일부 조건만 다루고 세부 조건·예외·운영 기준이 빠짐.',
    '- 이름만 반영: 노드 명칭은 닿으나 본문이 요구 핵심을 실질적으로 충족하지 못함.',
    '- 미반영: 본문이 요구를 거의 다루지 않음(막연한 참조뿐).',
    '- 범위밖: decision이 삭제(범위밖)인 건(품질 평가 대상 아님).',
    '',
    '## 출력 필드 (12건 전부)',
    '- grade: 위 5종 중 하나.',
    '- representative_node: 판정 근거가 된 핵심 노드 ID 1개(node_bodies에 있는 것).',
    '- evidence: 그 노드 본문의 어느 문장이 충족/불충족인지 구체 인용(1~2문장).',
    '- gap: 부족한 조건(충실 반영·범위밖이면 "-").',
    '- proposed_backlog: 갭 주제 태그(예: BL-HUB-컨텍스트전달, BL-HUB-운영자도구). 갭 없으면 "-".',
    "- 어떤 필드에도 '|' 문자 금지.",
    '',
    '## 산출 (반드시 둘 다)',
    '(A) grades 배열(12건)을 schema로 반환.',
    `(B) 동일 배열을 ${WORK}/qa_b${i}.json 에 Write.`,
    '엄정하게 평가하라. 본문이 요구를 직접 충족할 때만 충실 반영을 부여하라.',
  ].join('\n')
}

function advPrompt(i, qa) {
  return [
    '너는 품질 평가를 회의적으로 검증하는 적대적 검토자다. 과대평가(특히 충실 반영 남발)를 잡는 것이 임무다.',
    `## QA 1차 판정 결과(배치 ${i + 1}):`,
    JSON.stringify((qa && qa.grades) || [], null, 1),
    '',
    `## Read: ${WORK}/qa_input_b${i}.json — 요구 원문과 node_bodies(실제 정책 본문).`,
    '',
    '## 검증 규칙',
    "- 1차에서 '충실 반영'으로 판정된 건을 표적으로, 본문이 요구의 핵심 조건을 정말 직접 충족하는지 의심하라. 막연하거나 상위개념만 있으면 challenge='강등 제안' + revised_grade(부분 반영/이름만 반영).",
    "- 나머지 등급(부분/이름만/미반영/범위밖)은 원칙적으로 challenge='동의'. 단 명백히 과소평가됐다면 challenge='승급 제안'.",
    '- counter_evidence: 강등/승급 근거를 본문 인용으로(동의면 한 줄 사유).',
    '- 12건 전부 reviews에 포함. original_grade는 QA 등급 그대로, challenge=동의면 revised_grade=original_grade.',
    "- '|' 문자 금지.",
    '',
    '## 산출 (반드시 둘 다)',
    '(A) reviews 배열(12건)을 schema로 반환.',
    `(B) 동일 배열을 ${WORK}/adv_b${i}.json 에 Write.`,
  ].join('\n')
}

const out = await pipeline(
  Array.from({ length: NB }, (_, k) => k),
  (i) => agent(qaPrompt(i), { schema: QA_SCHEMA, label: `qa:b${i + 1}`, phase: '품질평가' }),
  (qa, i) => agent(advPrompt(i, qa), { schema: ADV_SCHEMA, label: `adv:b${i + 1}`, phase: '적대검증' })
)
return { batches_done: out.filter(Boolean).length }
