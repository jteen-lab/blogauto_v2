/**
 * FABButton 컴포넌트
 * PC와 모바일에서 다른 형태로 표시되는 플로팅 액션 버튼
 */

class FABButton {
  constructor(options) {
    this.options = {
      text: '새로 만들기',
      icon: 'plus',
      onClick: null,
      href: null,
      position: 'bottom-right', // bottom-right, bottom-left, top-right, top-left
      theme: 'primary', // primary, secondary, success, warning, danger
      ...options
    };

    this.element = null;
    this.init();
  }

  init() {
    this.createElement();
    this.attachEvents();
  }

  createElement() {
    const container = document.createElement('div');
    container.className = 'fab-container';

    // PC 버전 생성
    const pcButton = this.createPCButton();
    container.appendChild(pcButton);

    // 모바일 FAB 생성
    const fabButton = this.createFABButton();
    container.appendChild(fabButton);

    this.element = container;
  }

  createPCButton() {
    const button = document.createElement(this.options.href ? 'a' : 'button');

    if (this.options.href) {
      button.href = this.options.href;
    }

    button.className = `hidden md:inline-flex items-center gap-2 px-4 py-2 rounded-lg
                      transition-all duration-200 ease-in-out focus:outline-none
                      focus:ring-2 focus:ring-offset-2 ${this.getThemeClasses()}`;

    button.innerHTML = `
      ${this.getIconSVG()}
      <span class="font-medium">${this.options.text}</span>
    `;

    return button;
  }

  createFABButton() {
    const fab = document.createElement(this.options.href ? 'a' : 'button');

    if (this.options.href) {
      fab.href = this.options.href;
    }

    const positionClass = this.getPositionClass();

    fab.className = `md:hidden fixed w-14 h-14 rounded-full shadow-lg z-50
                    flex items-center justify-center transition-all duration-200 ease-in-out
                    focus:outline-none focus:ring-2 focus:ring-offset-2 fab-ripple
                    transform hover:scale-105 ${positionClass} ${this.getThemeClasses()}`;

    fab.innerHTML = this.getIconSVG();

    return fab;
  }

  getThemeClasses() {
    const themes = {
      primary: 'bg-blue-600 hover:bg-blue-700 text-white focus:ring-blue-500 shadow-blue-500/25 hover:shadow-blue-500/40',
      secondary: 'bg-gray-600 hover:bg-gray-700 text-white focus:ring-gray-500 shadow-gray-500/25 hover:shadow-gray-500/40',
      success: 'bg-green-600 hover:bg-green-700 text-white focus:ring-green-500 shadow-green-500/25 hover:shadow-green-500/40',
      warning: 'bg-yellow-600 hover:bg-yellow-700 text-white focus:ring-yellow-500 shadow-yellow-500/25 hover:shadow-yellow-500/40',
      danger: 'bg-red-600 hover:bg-red-700 text-white focus:ring-red-500 shadow-red-500/25 hover:shadow-red-500/40'
    };

    return themes[this.options.theme] || themes.primary;
  }

  getPositionClass() {
    const positions = {
      'bottom-right': 'bottom-6 right-6',
      'bottom-left': 'bottom-6 left-6',
      'top-right': 'top-6 right-6',
      'top-left': 'top-6 left-6'
    };

    return positions[this.options.position] || positions['bottom-right'];
  }

  getIconSVG() {
    const icons = {
      plus: 'M12 4v16m8-8H4',
      edit: 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z',
      settings: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z',
      search: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
      home: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6'
    };

    const iconPath = icons[this.options.icon] || icons.plus;
    const iconSize = this.options.href || !window.matchMedia('(max-width: 768px)').matches ? 'w-5 h-5' : 'w-6 h-6';

    return `
      <svg class="${iconSize}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${iconPath}"/>
      </svg>
    `;
  }

  attachEvents() {
    if (this.options.onClick && typeof this.options.onClick === 'function') {
      const buttons = this.element.querySelectorAll('button');
      buttons.forEach(button => {
        button.addEventListener('click', (e) => {
          e.preventDefault();
          this.addRippleEffect(e);
          this.options.onClick(e);
        });
      });
    }

    // FAB에 리플 효과 추가
    const fabs = this.element.querySelectorAll('.fab-ripple');
    fabs.forEach(fab => {
      fab.addEventListener('click', this.addRippleEffect.bind(this));
    });
  }

  addRippleEffect(e) {
    const fab = e.currentTarget;
    const ripple = document.createElement('span');
    const rect = fab.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const x = e.clientX - rect.left - size / 2;
    const y = e.clientY - rect.top - size / 2;

    ripple.style.cssText = `
      position: absolute;
      width: ${size}px;
      height: ${size}px;
      left: ${x}px;
      top: ${y}px;
      background: rgba(255, 255, 255, 0.3);
      border-radius: 50%;
      transform: scale(0);
      animation: ripple 0.6s linear;
      pointer-events: none;
    `;

    fab.appendChild(ripple);

    setTimeout(() => {
      ripple.remove();
    }, 600);
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

  updateOptions(newOptions) {
    this.options = { ...this.options, ...newOptions };
    this.remove();
    this.init();
  }
}

// CSS 애니메이션 추가
if (!document.querySelector('#fab-styles')) {
  const style = document.createElement('style');
  style.id = 'fab-styles';
  style.textContent = `
    @keyframes ripple {
      to {
        transform: scale(2);
        opacity: 0;
      }
    }

    .fab-container {
      pointer-events: none;
    }

    .fab-container > * {
      pointer-events: auto;
    }
  `;
  document.head.appendChild(style);
}

// 전역으로 사용할 수 있도록 window 객체에 추가
window.FABButton = FABButton;