/**
 * 표 셀 슬라이드 — 넘치는 셀 내용을 가로로 흘려 전부 보여준다.
 *
 * 카드에서 쓰던 방식과 같지만 측정 시점이 다르다. 카드는 늘 보이는
 * 자리에 있었고, 표는 **탭 뒤에 숨어 있다.** 숨은 동안에는 폭이 0이라
 * 측정할 수 없고, 그때 한 번 재고 끝내면 탭을 열어도 영영 안 흐른다.
 * 그래서 ResizeObserver 로 폭이 생기는 순간을 기다린다.
 *
 * 순서도: docs/flowcharts/list_table_cell_slide.md
 */

/** 글자 수에 맞춘 속도(초). 길수록 느리게 — 읽을 시간을 준다. */
function cellSlideDuration(text) {
    const length = (text || '').length;
    return Math.max(14, Math.min(48, 10 + length * 0.28));
}

/**
 * 넘치는지 재서 흐를지 정한다.
 * @param {HTMLElement} el .cell-slide 요소
 */
function initCellSlide(el) {
    if (!el) return;
    const track = el.querySelector('.cell-slide-track');
    if (!track) return;

    const measure = () => {
        const width = el.clientWidth;
        if (width === 0) return false;   // 아직 숨어 있다

        // 복제본이 숨어 있으면 폭을 잴 수 없다. 잠시 풀고 잰다.
        const wasStatic = track.classList.contains('no-slide');
        track.classList.remove('no-slide');
        const half = track.scrollWidth / 2;
        if (half <= width) track.classList.add('no-slide');
        else if (wasStatic) { /* 넘친다 — no-slide 를 뗀 상태 유지 */ }
        return true;
    };

    if (measure()) {
        // 창 크기가 바뀌면 넘침 여부도 바뀐다. 관찰은 계속 둔다.
        observeCellSlide(el, measure);
        return;
    }
    observeCellSlide(el, measure);
}

/** 폭 변화를 계속 지켜본다. 탭 열림·창 크기 변경 모두 여기서 잡힌다. */
function observeCellSlide(el, measure) {
    if (el._cellSlideObserver || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => measure());
    observer.observe(el);
    el._cellSlideObserver = observer;
}

/**
 * 모바일 탭 일시정지. hover 가 없는 화면에서 멈춰 읽을 방법이 이것뿐이다.
 */
function toggleCellSlideTouch(event, el) {
    if (!el) return;
    const track = el.querySelector('.cell-slide-track');
    if (!track || track.classList.contains('no-slide')) return;
    track.classList.toggle('paused');
    el.classList.toggle('touch-paused');
}
