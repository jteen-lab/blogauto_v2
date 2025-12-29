/**
 * SelectionPopup 컴포넌트
 * 선택 옵션을 제공하는 모달 팝업
 */

class SelectionPopup {
  constructor(options) {
    this.options = {
      title: '선택하세요',
      options: [],
      cancelText: '취소',
      onSelect: null,
      onCancel: null,
      backdropDismiss: true,
      ...options
    };

    this.id = this.generateId();
    this.isOpen = false;
    this.element = null;
    this.backdrop = null;

    this.init();
  }

  generateId() {
    return 'selectionPopup-' + Math.random().toString(36).substr(2, 9);
  }

  init() {
    this.createElement();
    this.attachEvents();
  }

  createElement() {
    // 백드롭 생성
    this.backdrop = document.createElement('div');
    this.backdrop.id = this.id + '-backdrop';
    this.backdrop.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 hidden transition-opacity duration-200';

    if (this.options.backdropDismiss) {
      this.backdrop.addEventListener('click', () => this.close());
    }

    // 팝업 생성
    this.element = document.createElement('div');
    this.element.id = this.id;
    this.element.className = 'fixed inset-0 z-50 flex items-center justify-center p-4 hidden';

    this.element.innerHTML = this.createContent();

    // DOM에 추가
    document.body.appendChild(this.backdrop);
    document.body.appendChild(this.element);
  }

  createContent() {
    const optionsGrid = this.createOptionsGrid();

    return `
      <div class="bg-white rounded-xl shadow-2xl max-w-sm w-full transform scale-95 transition-transform duration-200"
           onclick="event.stopPropagation()">

        <!-- 헤더 -->
        <div class="p-6 pb-4">
          <div class="flex justify-between items-center">
            <h3 class="text-xl font-semibold text-gray-900">${this.options.title}</h3>
            <button class="close-btn p-1 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100 transition-colors">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- 옵션 그리드 -->
        <div class="px-6 pb-6">
          <div class="options-grid grid gap-3 ${this.getGridCols()}">
            ${optionsGrid}
          </div>
        </div>

        <!-- 취소 버튼 -->
        <div class="px-6 pb-6">
          <button class="cancel-btn w-full py-3 text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors">
            ${this.options.cancelText}
          </button>
        </div>

      </div>
    `;
  }

  createOptionsGrid() {
    if (!this.options.options || this.options.options.length === 0) {
      return '<div class="text-center text-gray-500 py-8">옵션이 없습니다</div>';
    }

    return this.options.options.map((option, index) => `
      <button class="option-btn flex flex-col items-center p-4 border-2 border-gray-200 rounded-xl hover:border-blue-300 hover:bg-blue-50 transition-all duration-200 group"
              data-action="${option.action || index}"
              data-text="${option.text || ''}">
        <span class="text-3xl mb-2 group-hover:scale-110 transition-transform duration-200">
          ${option.icon || this.getDefaultIcon(index)}
        </span>
        <span class="font-medium text-gray-900 group-hover:text-blue-700">${option.text}</span>
        ${option.description ? `<span class="text-xs text-gray-500 mt-1">${option.description}</span>` : ''}
      </button>
    `).join('');
  }

  getGridCols() {
    const count = this.options.options.length;
    if (count <= 2) return 'grid-cols-2';
    if (count <= 3) return 'grid-cols-3';
    if (count <= 4) return 'grid-cols-2';
    return 'grid-cols-3';
  }

  getDefaultIcon(index) {
    const icons = ['📋', '📝', '📦', '⚙️', '🔧', '📊', '📈', '💡'];
    return icons[index % icons.length];
  }

  attachEvents() {
    // 닫기 버튼
    const closeBtn = this.element.querySelector('.close-btn');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.close());
    }

    // 취소 버튼
    const cancelBtn = this.element.querySelector('.cancel-btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        if (this.options.onCancel) {
          this.options.onCancel();
        }
        this.close();
      });
    }

    // 옵션 버튼들
    const optionBtns = this.element.querySelectorAll('.option-btn');
    optionBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const action = e.currentTarget.dataset.action;
        const text = e.currentTarget.dataset.text;

        if (this.options.onSelect) {
          this.options.onSelect(action, text, e.currentTarget);
        }

        // 커스텀 이벤트 발생
        const event = new CustomEvent('selection-popup:select', {
          detail: { action, text, popup: this }
        });
        document.dispatchEvent(event);

        this.close();
      });
    });

    // ESC 키
    this.escKeyHandler = (e) => {
      if (e.key === 'Escape' && this.isOpen) {
        this.close();
      }
    };
    document.addEventListener('keydown', this.escKeyHandler);
  }

  open() {
    if (this.isOpen) return;

    // 백드롭 표시
    this.backdrop.classList.remove('hidden');
    setTimeout(() => {
      this.backdrop.style.opacity = '1';
    }, 10);

    // 팝업 표시
    this.element.classList.remove('hidden');

    // 애니메이션
    const content = this.element.querySelector('div > div');
    if (content) {
      setTimeout(() => {
        content.classList.remove('scale-95');
        content.classList.add('scale-100');
      }, 10);
    }

    // 스크롤 방지
    document.body.style.overflow = 'hidden';

    this.isOpen = true;
  }

  close() {
    if (!this.isOpen) return;

    const content = this.element.querySelector('div > div');

    // 애니메이션
    if (content) {
      content.classList.remove('scale-100');
      content.classList.add('scale-95');
    }

    // 백드롭 숨기기
    this.backdrop.style.opacity = '0';

    setTimeout(() => {
      this.element.classList.add('hidden');
      this.backdrop.classList.add('hidden');
    }, 200);

    // 스크롤 복원
    document.body.style.overflow = '';

    this.isOpen = false;
  }

  updateOptions(newOptions) {
    this.options.options = newOptions;
    const optionsGrid = this.element.querySelector('.options-grid');
    if (optionsGrid) {
      optionsGrid.className = `options-grid grid gap-3 ${this.getGridCols()}`;
      optionsGrid.innerHTML = this.createOptionsGrid();

      // 새로운 옵션 버튼들에 이벤트 리스너 추가
      const optionBtns = optionsGrid.querySelectorAll('.option-btn');
      optionBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
          const action = e.currentTarget.dataset.action;
          const text = e.currentTarget.dataset.text;

          if (this.options.onSelect) {
            this.options.onSelect(action, text, e.currentTarget);
          }

          const event = new CustomEvent('selection-popup:select', {
            detail: { action, text, popup: this }
          });
          document.dispatchEvent(event);

          this.close();
        });
      });
    }
  }

  updateTitle(newTitle) {
    this.options.title = newTitle;
    const titleElement = this.element.querySelector('h3');
    if (titleElement) {
      titleElement.textContent = newTitle;
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

  // 정적 메서드들
  static create(options) {
    return new SelectionPopup(options);
  }

  static show(title, options, onSelect) {
    const popup = new SelectionPopup({
      title,
      options,
      onSelect: (action, text) => {
        if (onSelect) onSelect(action, text);
        popup.destroy();
      },
      onCancel: () => {
        popup.destroy();
      }
    });

    popup.open();
    return popup;
  }

  static confirm(title, message, confirmText = '확인', cancelText = '취소') {
    return new Promise((resolve) => {
      const popup = new SelectionPopup({
        title,
        options: [
          { text: cancelText, icon: '❌', action: 'cancel' },
          { text: confirmText, icon: '✅', action: 'confirm' }
        ],
        onSelect: (action) => {
          popup.destroy();
          resolve(action === 'confirm');
        },
        onCancel: () => {
          popup.destroy();
          resolve(false);
        }
      });

      // 메시지 추가
      popup.open();
      const optionsContainer = popup.element.querySelector('.px-6.pb-6');
      if (message && optionsContainer) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'mb-4 text-gray-600 text-center';
        messageDiv.textContent = message;
        optionsContainer.insertBefore(messageDiv, optionsContainer.firstChild);
      }
    });
  }
}

// CSS 스타일 추가
if (!document.querySelector('#selection-popup-styles')) {
  const style = document.createElement('style');
  style.id = 'selection-popup-styles';
  style.textContent = `
    .group:hover .group-hover\\:scale-110 {
      transform: scale(1.1);
    }

    .group:hover .group-hover\\:text-blue-700 {
      color: rgb(29 78 216);
    }

    .option-btn:focus {
      outline: 2px solid rgb(59 130 246);
      outline-offset: 2px;
    }

    .transform {
      transition: transform 0.2s cubic-bezier(0.4, 0.0, 0.2, 1);
    }
  `;
  document.head.appendChild(style);
}

// 전역으로 사용할 수 있도록 window 객체에 추가
window.SelectionPopup = SelectionPopup;