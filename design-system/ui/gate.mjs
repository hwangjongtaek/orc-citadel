/**
 * Citadel Gate(브리핑 대시보드) 공용 컴포넌트 — 목업·앱이 공유한다 (TS-2·TS-3).
 *
 * 데이터 무지(props-only): 목업은 fixture 를, 앱은 /api/* 매핑값을 넘긴다.
 * URL 공간은 `urls`(shell.mjs 의 MOCKUP_URLS/APP_URLS)로 주입한다.
 */

import {h, Card, Badge, Text, Button, confidence, grid, id} from './components.mjs';
import {MOCKUP_URLS} from './shell.mjs';

const PROCESS = [
  ['char-scout.png', 'Scouts', '근거 수집'],
  ['char-seer.png', 'Seers · Council', '그래프 조사 · 반증'],
  ['char-warchief.png', '보고서', '근거로 답'],
];

const link = (href, label) =>
  h('a', {href, style: {fontFamily: 'var(--font-family-heading)', fontSize: 11.5,
    fontWeight: 600, color: 'var(--color-accent)', textDecoration: 'none'}}, label);

/** 브랜드 블록 — lockup 분리 자산 (FR-4). */
export function brandBlock({urls = MOCKUP_URLS} = {}) {
  return h('div', {style: {display: 'flex', alignItems: 'center', gap: 20, marginBottom: 20}},
    h('img', {src: urls.asset('logo-mark.png'), alt: 'Orc Citadel 문장',
      style: {height: 96, width: 'auto', flex: 'none'}}),
    h('div', {},
      h('img', {src: urls.asset('logo-title.png'), alt: 'ORC CITADEL',
        style: {height: 46, width: 'auto', display: 'block'}}),
      h('div', {style: {marginTop: 8}},
        h(Text, {type: 'supporting'}, 'The Camp works. The Citadel remembers.')),
      h('div', {style: {marginTop: 2}},
        h(Text, {type: 'supporting'},
          'Temporal Evidence Intelligence · 시간을 기억하는 증거 정보 본부')),
      h('div', {style: {marginTop: 8}},
        link(urls.about, '프로젝트 안내'))));
}

/** subject 결론 카드 — confidence 는 값+근거+독립 출처 병기 (단일 게이지 금지). */
export function conclusionCard({badge, cid, subject, statement, conf, ev, indep,
                                urls = MOCKUP_URLS}) {
  return h(Card, {key: cid}, h('div', {style: {padding: 4}},
    h('div', {style: {display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}},
      h(Badge, badge), id(cid)),
    h('div', {style: {marginTop: 8, fontFamily: 'var(--font-family-heading)',
      fontSize: 14, fontWeight: 600, color: 'var(--color-text-primary)'}}, subject),
    h('div', {style: {marginTop: 6, minHeight: 60}},
      h(Text, {type: 'supporting'}, statement)),
    h('div', {style: {marginTop: 10}}, confidence(conf, ev, indep)),
    h('div', {style: {display: 'flex', gap: 16, marginTop: 12}},
      link(urls.page('war-table'), 'War Table에서 보기 →'),
      link(urls.page('hall-of-witnesses'), '근거 열람 · Witnesses →'))));
}

/** 최근 변화 카드 — confidence 델타·반증·신규 근거. */
export function changeCard({kind, tone, subject, delta, note, ref, urls = MOCKUP_URLS}) {
  return h(Card, {key: ref}, h('div', {style: {padding: 4}},
    h('div', {style: {display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', gap: 8}},
      h(Badge, {variant: tone, label: kind}), id(ref)),
    h('div', {style: {marginTop: 8, display: 'flex', alignItems: 'baseline', gap: 8,
      flexWrap: 'wrap'}},
      h('span', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 13,
        fontWeight: 600, color: 'var(--color-text-primary)'}}, subject),
      h('span', {style: {fontFamily: 'var(--font-family-code)', fontSize: 12,
        color: 'var(--color-accent)'}}, delta)),
    h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, note)),
    h('div', {style: {marginTop: 8}},
      h('a', {href: urls.page('signal-spire'),
        style: {fontFamily: 'var(--font-family-heading)',
          fontSize: 11.5, fontWeight: 600, color: 'var(--color-accent)',
          textDecoration: 'none'}}, 'Signal Spire에서 보기 →'))));
}

/**
 * New Campaign — 조사 지시 진입점. 질문을 Council Chamber 로 넘긴다.
 *
 * 그래프·존은 여전히 read-only(§3-3) — 조사 실행이 쓰는 것은 investigation
 * metadata(PostgreSQL) 뿐이고, 근거는 이미 축적된 범위에서만 읽는다.
 * JS 없이 동작하는 GET form 이라 목업·앱이 같은 마크업을 쓴다 (질문은 `question`
 * 쿼리로 전달 — Council 이 받아 지시 입력을 채운다).
 */
export function newCampaignCard({urls = MOCKUP_URLS} = {}) {
  return h(Card, {}, h('form', {method: 'get', action: urls.page('council-chamber'),
    style: {padding: 4}},
    h('div', {style: {display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', gap: 12, flexWrap: 'wrap'}},
      h('div', {},
        h(Text, {}, 'New Campaign · 새 조사 요청'),
        h('div', {style: {marginTop: 4}},
          h(Text, {type: 'supporting'},
            '자연어 질문 → Council 이 계획을 세우고 Scouts 가 근거를 수집'))),
      h(Badge, {variant: 'neutral', label: '조사 지시 → Council Chamber'})),

    h('div', {style: {display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
      margin: '16px 0'}},
      ...PROCESS.flatMap(([art, name, role], i) => [
        i ? h('span', {key: `a${i}`, style: {color: 'var(--color-text-secondary)'}}, '→') : null,
        h('div', {key: name, style: {display: 'flex', alignItems: 'center', gap: 8}},
          h('img', {src: urls.asset(art), alt: '',
            style: {width: 40, height: 40, imageRendering: 'pixelated',
              borderRadius: 'var(--radius-inner)', flex: 'none'}}),
          h('div', {},
            h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 12,
              fontWeight: 600, color: 'var(--color-text-primary)'}}, name),
            h(Text, {type: 'supporting'}, role)))])),

    h('input', {type: 'text', name: 'question',
      placeholder: '예) 2024년 이후 A사의 AI 가속기 공급망 다변화가 실제로 진행되었는가?',
      style: {width: '100%', boxSizing: 'border-box',
        padding: '10px 12px', background: 'var(--color-background-muted)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-element)', color: 'var(--color-text-primary)',
        fontSize: 13, outline: 'none'}}),

    h('div', {style: {display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', gap: 12, marginTop: 14, flexWrap: 'wrap'}},
      h(Text, {type: 'supporting'},
        '그래프·존은 read-only(§3-3) — 조사는 이미 축적된 근거 범위에서 실행되고, '
        + '남는 것은 investigation metadata 뿐이다. 근거가 없으면 gap 으로 표기된다.'),
      h(Button, {type: 'submit', variant: 'primary'}, '조사 지시 · Council Chamber →'))));
}

/** 공간 빠른 진입 카드 그리드. */
export function quickEntry(spaces, urls = MOCKUP_URLS) {
  return grid(4, 16, ...spaces.map(([slug, name, role]) =>
    h('a', {key: slug, href: urls.page(slug), style: {textDecoration: 'none'}},
      h(Card, {}, h('div', {style: {padding: 4}},
        h('div', {style: {fontFamily: 'var(--font-family-heading)', fontSize: 13,
          fontWeight: 600, color: 'var(--color-text-primary)'}}, name),
        h('div', {style: {marginTop: 4}}, h(Text, {type: 'supporting'}, role)))))));
}
