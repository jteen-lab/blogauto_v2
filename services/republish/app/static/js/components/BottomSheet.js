/**
 * BottomSheet 컴포넌트
 * 모바일에서 하단에서 올라오는 시트 UI
 */

class BottomSheet {
  constructor(options) {
    this.options = {
      title: '',
      content: '',
      showHandle: true,
      backdropDismiss: true,
      swipeToClose: true,
      maxHeight: '80vh',
      onOpen: null,
      onClose: null,
      ...options
    };

    this.id = this.generateId();
    this.isOpen = false;
    this.startY = 0;
    this.currentY = 0;
    this.isDragging = false;

    this.element = null;
    this.backdrop = null;

    this.init();
  }

  generateId() {
    return 'bottomSheet-' + Math.random().toString(36).substr(2, 9);
  }

  init() {
    this.createElement();
    this.attachEvents();
  }

  createElement() {
    // 백드롭 생성
    this.backdrop = document.createElement('div');
    this.backdrop.id = this.id + '-backdrop';
    this.backdrop.className = 'fixed inset-0 bg-black bg-opacity-50 z-40 hidden transition-opacity duration-300';

    if (this.options.backdropDismiss) {
      this.backdrop.addEventListener('click', () => this.close());
    }

    // 바텀시트 생성
    this.element = document.createElement('div');
    this.element.id = this.id;
    this.element.className = `fixed inset-x-0 bottom-0 bg-white rounded-t-2xl shadow-2xl z-50
                            transform translate-y-full transition-transform duration-300 ease-out`;

    this.element.style.maxHeight = this.options.maxHeight;

    this.element.innerHTML = this.createContent();

    // DOM에 추가
    document.body.appendChild(this.backdrop);
    document.body.appendChild(this.element);
  }

  createContent() {
    const handleBar = this.options.showHandle ? `
      <div class="flex justify-center pt-3 pb-2">
        <div class="w-12 h-1 bg-gray-300 rounded-full"></div>
      </div>
    ` : '';

    const header = this.options.title ? `
      <div class="flex justify-between items-center px-4 py-3 border-b border-gray-200">
        <h3 class="text-lg font-semibold text-gray-900">${this.options.title}</h3>
        <button class="close-btn p-1 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>
    ` : '';

    return `
      ${handleBar}
      ${header}
      <div class="content-area p-4 overflow-y-auto">
        ${this.options.content}
      </div>
      <div style="height: env(safe-area-inset-bottom);"></div>
    `;
  }

  attachEvents() {
    // 닫기 버튼 이벤트
    const closeBtn = this.element.querySelector('.close-btn');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.close());
    }

    // 스와이프 이벤트
    if (this.options.swipeToClose) {
      this.attachSwipeEvents();
    }

    // ESC 키 이벤트
    this.escKeyHandler = (e) => {
      if (e.key === 'Escape' && this.isOpen) {
        this.close();
      }
    };
    document.addEventListener('keydown', this.escKeyHandler);
  }

  attachSwipeEvents() {
    this.element.addEventListener('touchstart', (e) => {
      this.startY = e.touches[0].clientY;
      this.isDragging = true;
    }, { passive: true });

    this.element.addEventListener('touchmove', (e) => {
      if (!this.isDragging) return;

      this.currentY = e.touches[0].clientY;
      const deltaY = this.currentY - this.startY;

      // 아래로 드래그할 때만
      if (deltaY > 0) {
        this.element.style.transform = `translateY(${deltaY}px)`;
      }
    }, { passive: true });

    this.element.addEventListener('touchend', () => {
      if (!this.isDragging) return;

      this.isDragging = false;
      const deltaY = this.currentY - this.startY;

      // 일정 거리 이상 드래그하면 닫기
      if (deltaY > 100) {
        this.close();
      } else {
        // 원래 위치로 복원
        this.element.style.transform = '';
      }
    });
  }

  open(content) {
    if (this.isOpen) return;

    // 내용 업데이트
    if (content) {
      this.updateContent(content);
    }

    // 백드롭 표시
    this.backdrop.classList.remove('hidden');
    setTimeout(() => {
      this.backdrop.style.opacity = '1';
    }, 10);

    // 시트 표시
    this.element.classList.remove('translate-y-full');

    // 스크롤 방지
    document.body.style.overflow = 'hidden';

    this.isOpen = true;

    // 콜백 실행
    if (this.options.onOpen) {
      this.options.onOpen(this);
    }
  }

  close() {
    if (!this.isOpen) return;

    // 시트 숨기기
    this.element.classList.add('translate-y-full');

    // 백드롭 숨기기
    this.backdrop.style.opacity = '0';
    setTimeout(() => {
      this.backdrop.classList.add('hidden');
    }, 300);

    // 스크롤 복원
    document.body.style.overflow = '';

    this.isOpen = false;

    // 콜백 실행
    if (this.options.onClose) {
      this.options.onClose(this);
    }
  }

  toggle(content) {
    if (this.isOpen) {
      this.close();
    } else {
      this.open(content);
    }
  }

  updateContent(content) {
    const contentArea = this.element.querySelector('.content-area');
    if (contentArea) {
      contentArea.innerHTML = content;
    }
  }

  updateTitle(title) {
    this.options.title = title;
    const titleElement = this.element.querySelector('h3');
    if (titleElement) {
      titleElement.textContent = title;
    }
  }

  destroy() {
    // 이벤트 리스너 제거
    document.removeEventListener('keydown', this.escKeyHandler);

    // DOM 요소 제거
    if (this.backdrop && this.backdrop.parentNode) {
      this.backdrop.parentNode.removeChild(this.backdrop);
    }

    if (this.element && this.element.parentNode) {
      this.element.parentNode.removeChild(this.element);
    }

    // 스크롤 복원
    document.body.style.overflow = '';
  }

  // 정적 메서드: 간단한 사용을 위한 헬퍼
  static create(options) {
    return new BottomSheet(options);
  }

  static prompt(title, content, buttons = []) {
    const buttonsHtml = buttons.map(button => `
      <button class="w-full p-3 text-left hover:bg-gray-50 border-b border-gray-100 last:border-b-0"
              data-action="${button.action || ''}"
              onclick="this.closest('.fixed').dispatchEvent(new CustomEvent('bottomsheet-action', {detail: '${button.action || ''}'}))"
              ${button.className ? `class="${button.className}"` : ''}>
        ${button.icon ? `<span class="mr-3">${button.icon}</span>` : ''}
        ${button.text}
      </button>
    `).join('');

    const sheet = new BottomSheet({
      title,
      content: content + `<div class="mt-4 -mx-4 -mb-4">${buttonsHtml}</div>`,
      backdropDismiss: true
    });

    return new Promise((resolve) => {
      sheet.element.addEventListener('bottomsheet-action', (e) => {
        const action = e.detail;
        sheet.close();
        resolve(action);
      });

      sheet.open();
    });
  }
}

// CSS 스타일 추가
if (!document.querySelector('#bottom-sheet-styles')) {
  const style = document.createElement('style');
  style.id = 'bottom-sheet-styles';
  style.textContent = `
    /* 스크롤바 스타일링 */
    .overflow-y-auto::-webkit-scrollbar {
      width: 4px;
    }

    .overflow-y-auto::-webkit-scrollbar-track {
      background: transparent;
    }

    .overflow-y-auto::-webkit-scrollbar-thumb {
      background-color: rgba(156, 163, 175, 0.5);
      border-radius: 2px;
    }

    .overflow-y-auto::-webkit-scrollbar-thumb:hover {
      background-color: rgba(156, 163, 175, 0.8);
    }

    /* 드래그 중 선택 방지 */
    .dragging {
      user-select: none;
      -webkit-user-select: none;
    }
  `;
  document.head.appendChild(style);
}

// 전역으로 사용할 수 있도록 window 객체에 추가
window.BottomSheet = BottomSheet;