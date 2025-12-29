/**
 * StatusBadge 컴포넌트
 * 상태에 따른 뱃지 표시
 */

class StatusBadge {
  constructor(options) {
    this.options = {
      status: 'inactive',
      text: '',
      size: 'sm',
      withIcon: false,
      animated: false,
      ...options
    };

    this.element = null;
    this.init();
  }

  static statusMap = {
    active: '활성',
    inactive: '비활성',
    paused: '일시정지',
    running: '실행중',
    stopped: '중지됨',
    pending: '대기중',
    completed: '완료',
    error: '오류',
    success: '성공',
    warning: '주의',
    failed: '실패'
  };

  static statusColors = {
    active: 'bg-green-100 text-green-800 border-green-200',
    inactive: 'bg-gray-100 text-gray-600 border-gray-200',
    paused: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    running: 'bg-blue-100 text-blue-800 border-blue-200',
    stopped: 'bg-gray-100 text-gray-600 border-gray-200',
    pending: 'bg-orange-100 text-orange-800 border-orange-200',
    completed: 'bg-green-100 text-green-800 border-green-200',
    error: 'bg-red-100 text-red-800 border-red-200',
    success: 'bg-green-100 text-green-800 border-green-200',
    warning: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    failed: 'bg-red-100 text-red-800 border-red-200'
  };

  static statusIcons = {
    active: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
    inactive: 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z',
    paused: 'M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z',
    running: 'M14.828 14.828a4 4 0 01-5.656 0M9 10h1.586a1 1 0 01.707.293l2.414 2.414a1 1 0 00.707.293H15M9 10v4a2 2 0 002 2h2a2 2 0 002-2v-4M9 10V6a2 2 0 012-2h2a2 2 0 012 2v4',
    stopped: 'M21 12a9 9 0 11-18 0 9 9 0 0118 0z M15 12a3 3 0 11-6 0 3 3 0 016 0z',
    pending: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
    completed: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
    error: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z',
    success: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
    warning: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z',
    failed: 'M6 18L18 6M6 6l12 12'
  };

  static sizeClasses = {
    xs: 'px-2 py-1 text-xs',
    sm: 'px-2 py-1 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-2 text-base'
  };

  static iconSizes = {
    xs: 'w-3 h-3',
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-5 h-5'
  };

  init() {
    this.createElement();
  }

  createElement() {
    this.element = document.createElement('span');
    this.updateElement();
  }

  updateElement() {
    const status = this.options.status;
    const text = this.options.text || StatusBadge.statusMap[status] || status;
    const size = this.options.size;
    const withIcon = this.options.withIcon;
    const animated = this.options.animated;

    // 기본 클래스
    let className = `inline-flex items-center gap-1 rounded-full font-medium border transition-all duration-200
                    ${StatusBadge.sizeClasses[size] || StatusBadge.sizeClasses.sm}
                    ${StatusBadge.statusColors[status] || StatusBadge.statusColors.inactive}`;

    if (animated) {
      className += ' hover:scale-105';
    }

    this.element.className = className;

    // 내용 생성
    let content = '';

    // 아이콘 추가
    if (withIcon && StatusBadge.statusIcons[status]) {
      const iconSize = StatusBadge.iconSizes[size] || StatusBadge.iconSizes.sm;
      const animationClass = status === 'running' ? 'animate-spin' : '';

      content += `
        <svg class="${iconSize} ${animationClass}"
             fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="${StatusBadge.statusIcons[status]}"/>
        </svg>
      `;
    }

    // 텍스트 추가
    content += `<span>${text}</span>`;

    this.element.innerHTML = content;
  }

  updateStatus(newStatus, newText = null) {
    this.options.status = newStatus;
    if (newText !== null) {
      this.options.text = newText;
    }
    this.updateElement();
  }

  updateText(newText) {
    this.options.text = newText;
    this.updateElement();
  }

  updateSize(newSize) {
    this.options.size = newSize;
    this.updateElement();
  }

  toggleIcon() {
    this.options.withIcon = !this.options.withIcon;
    this.updateElement();
  }

  appendTo(parent) {
    if (typeof parent === 'string') {
      parent = document.querySelector(parent);
    }
    parent.appendChild(this.element);
  }

  remove() {
    if (this.element && this.element.parentNode) {
      this.element.parentNode.removeChild(this.element);
    }
  }

  // 정적 메서드들
  static create(options) {
    return new StatusBadge(options);
  }

  static createFromElement(element) {
    const status = element.dataset.status || 'inactive';
    const text = element.textContent.trim();
    const size = element.dataset.size || 'sm';
    const withIcon = element.dataset.icon === 'true';

    const badge = new StatusBadge({
      status,
      text,
      size,
      withIcon
    });

    element.parentNode.replaceChild(badge.element, element);
    return badge;
  }

  // 유틸리티 메서드들
  static getStatusColor(status) {
    return StatusBadge.statusColors[status] || StatusBadge.statusColors.inactive;
  }

  static getStatusText(status) {
    return StatusBadge.statusMap[status] || status;
  }

  static isActiveStatus(status) {
    return ['active', 'running', 'success', 'completed'].includes(status);
  }

  static isErrorStatus(status) {
    return ['error', 'failed'].includes(status);
  }

  static isWarningStatus(status) {
    return ['warning', 'paused', 'pending'].includes(status);
  }

  // 애니메이션 효과
  pulse() {
    this.element.classList.add('animate-pulse');
    setTimeout(() => {
      this.element.classList.remove('animate-pulse');
    }, 1000);
  }

  flash(color = 'bg-blue-200') {
    const originalClasses = this.element.className;
    this.element.className = this.element.className.replace(/bg-\w+-\d+/, color);

    setTimeout(() => {
      this.element.className = originalClasses;
    }, 300);
  }

  bounce() {
    this.element.classList.add('animate-bounce');
    setTimeout(() => {
      this.element.classList.remove('animate-bounce');
    }, 1000);
  }
}

// CSS 애니메이션 추가
if (!document.querySelector('#status-badge-styles')) {
  const style = document.createElement('style');
  style.id = 'status-badge-styles';
  style.textContent = `
    @keyframes spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }

    @keyframes bounce {
      0%, 20%, 53%, 80%, 100% {
        transform: translate3d(0,0,0);
      }
      40%, 43% {
        transform: translate3d(0, -10px, 0);
      }
      70% {
        transform: translate3d(0, -5px, 0);
      }
      90% {
        transform: translate3d(0, -2px, 0);
      }
    }

    .animate-spin {
      animation: spin 1s linear infinite;
    }

    .animate-pulse {
      animation: pulse 1s ease-in-out infinite;
    }

    .animate-bounce {
      animation: bounce 1s ease-in-out;
    }

    .status-badge:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    }
  `;
  document.head.appendChild(style);
}

// DOM이 로드된 후 자동 초기화
document.addEventListener('DOMContentLoaded', () => {
  // data-status-badge 속성을 가진 요소들을 자동으로 StatusBadge로 변환
  const elements = document.querySelectorAll('[data-status-badge]');
  elements.forEach(element => {
    StatusBadge.createFromElement(element);
  });
});

// 전역으로 사용할 수 있도록 window 객체에 추가
window.StatusBadge = StatusBadge;