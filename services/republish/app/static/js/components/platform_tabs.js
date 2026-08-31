/**
 * 플랫폼 탭 판정 — 플로우·오토런이 같은 규칙으로 나눈다.
 *
 * 두 화면이 각자 판정하면 같은 플로우가 화면마다 다른 탭에 들어간다.
 * 그런 어긋남은 눈에 잘 띄지 않으면서 계속 헷갈리게 만든다.
 *
 * 순서도: docs/flowcharts/flow_list_table.md
 */

/** 탭 순서. 표시 순서이자 "첫 번째로 항목이 있는 탭" 을 찾는 순서다. */
const PLATFORM_TAB_KEYS = ['wordpress', 'blogger', 'mixed', 'none'];

/**
 * 플랫폼 문자열 목록을 탭 키로 바꾼다.
 *
 * 'mixed' 는 지금 비어 있지만 반드시 있어야 한다. 두 플랫폼 블로그를 함께
 * 붙인 항목이 어느 탭에도 못 들어가면 화면에서 사라진다.
 *
 * @param {Array<string>} platforms 연결된 블로그들의 platform 값
 * @returns {'wordpress'|'blogger'|'mixed'|'none'}
 */
function platformTabOf(platforms) {
    const set = new Set((platforms || []).filter(Boolean));
    if (set.size === 0) return 'none';
    if (set.size > 1) return 'mixed';
    return set.has('wordpress') ? 'wordpress' : 'blogger';
}
