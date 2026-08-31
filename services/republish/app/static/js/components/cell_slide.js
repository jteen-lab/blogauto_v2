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
 *
 * 복제본을 펼쳐 재지 않는다. 펼치면 트랙이 두 배가 되고, 표가 자동
 * 레이아웃이면 그 순간 열이 넓어진다. 넓어진 것을 ResizeObserver 가
 * 다시 잡아 재고… 스크롤바가 깜빡이는 고리가 된다.
 * 대신 **항상 보이는 첫 항목**의 폭만 잰다.
 *
 * @param {HTMLElement} el .cell-slide 요소
 */
function initCellSlide(el) {
    if (!el) return;
    const track = el.querySelector('.cell-slide-track');
    const first = el.querySelector('.cell-slide-item');
    if (!track || !first) return;

    const measure = () => {
        const width = el.clientWidth;
        if (width === 0) return false;          // 아직 탭 뒤에 숨어 있다
        if (el._cellSlideWidth === width) return true;   // 같은 폭이면 다시 잴 것이 없다
        el._cellSlideWidth = width;

        // 첫 항목은 no-slide 여부와 무관하게 늘 보인다 → 클래스를 건드리지 않고 잰다.
        if (first.scrollWidth > width + 1) track.classList.remove('no-slide');
        else track.classList.add('no-slide');
        return true;
    };

    measure();
    // 폭이 0이었다가 탭이 열리는 경우, 창 크기가 바뀌는 경우 모두 여기서 잡는다.
    observeCellSlide(el, measure);
}

/** 폭 변화를 계속 지켜본다. 탭 열림·창 크기 변경 모두 여기서 잡힌다. */
function observeCellSlide(el, measure) {
    if (el._cellSlideObserver || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
        // 콜백 안에서 레이아웃을 바꾸면 같은 프레임에 다시 불릴 수 있다.
        // 다음 프레임으로 미뤄 되먹임을 끊는다.
        requestAnimationFrame(() => measure());
    });
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
