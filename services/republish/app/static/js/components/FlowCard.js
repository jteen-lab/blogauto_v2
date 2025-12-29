/**
 * FlowCard 컴포넌트
 * 플로우 정보와 상태를 표시하는 카드
 */

class FlowCard {
  constructor(options) {
    this.options = {
      flow: null,
      showActions: true,
      compact: false,
      selectable: false,
      onEdit: null,
      onDelete: null,
      onSelect: null,
      ...options
    };

    this.element = null;
    this.init();
  }

  static statusIcons = {
    active: '🟢',
    inactive: '⚪',
    paused: '🟡',
    running: '🔄',
    error: '🔴',
    completed: '✅'
  };

  init() {
    this.createElement();
  }

  createElement() {
    this.element = document.createElement('div');
    this.updateElement();
  }

  updateElement() {
    const flow = this.options.flow;
    if (!flow) {
      this.createEmptyCard();
      return;
    }

    const showActions = this.options.showActions;
    const compact = this.options.compact;
    const selectable = this.options.selectable;

    this.element.className = `bg-white rounded-lg border p-4 hover:shadow-md transition-shadow group
                             ${compact ? 'p-3' : ''}
                             ${selectable ? 'cursor-pointer hover:border-blue-300' : ''}`;

    this.element.setAttribute('data-flow-id', flow.id);

    this.element.innerHTML = `
      <div class="flex items-start justify-between">
        <div class="flex items-center gap-3 flex-1 min-w-0">
          <!-- 플로우 아이콘과 상태 -->
          <div class="relative">
            <span class="text-2xl">🔄</span>
            <span class="absolute -top-1 -right-1 text-xs">
              ${FlowCard.statusIcons[flow.status] || '⚪'}
            </span>
          </div>

          <div class="flex-1 min-w-0">
            <h4 class="font-medium text-gray-900 truncate">${flow.name}</h4>
            ${flow.description && !compact ?
              `<p class="text-sm text-gray-500 mt-1 line-clamp-2">${flow.description}</p>` : ''}

            <!-- 플로우 정보 -->
            <div class="flex items-center gap-3 mt-1 text-xs text-gray-500">
              <span>모듈 ${flow.modules?.length || 0}개</span>
              ${flow.total_executions ? `<span>실행 ${flow.total_executions}회</span>` : ''}
              ${flow.last_execution ? `<span>최근 ${this.formatTimeAgo(flow.last_execution)}</span>` : ''}
            </div>
          </div>
        </div>

        ${showActions ? this.createActionsHTML(flow.id) : ''}
      </div>

      ${!compact && flow.modules ? this.createModuleFlowHTML(flow.modules) : ''}

      ${selectable ? this.createSelectableHTML(flow.id) : ''}
    `;

    this.attachEvents();
  }

  createActionsHTML(flowId) {
    return `
      <div class="flex gap-1">
        <button class="edit-btn p-1 text-gray-400 hover:text-blue-600" title="수정">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
          </svg>
        </button>
        <button class="delete-btn p-1 text-gray-400 hover:text-red-600" title="삭제">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
          </svg>
        </button>
      </div>
    `;
  }

  createModuleFlowHTML(modules) {
    if (!modules || modules.length === 0) return '';

    const moduleItems = modules.map((module, index) => {
      const isLast = index === modules.length - 1;
      return `
        <div class="flex-shrink-0 flex items-center">
          <div class="px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs">
            ${module.name}
          </div>
          ${!isLast ? `
            <svg class="w-3 h-3 mx-1 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
            </svg>
          ` : ''}
        </div>
      `;
    }).join('');

    return `
      <div class="mt-3 pt-3 border-t border-gray-100">
        <div class="flex items-center gap-2 overflow-x-auto">
          ${moduleItems}
        </div>
      </div>
    `;
  }

  createSelectableHTML(flowId) {
    return `
      <div class="flex items-center justify-between pt-3 border-t border-gray-100">
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" name="selected_flows" value="${flowId}"
                 class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500">
          <span class="text-sm text-gray-600">선택</span>
        </label>
      </div>
    `;
  }

  createEmptyCard() {
    this.element.className = 'bg-white rounded-lg border border-gray-200 p-4 animate-pulse';
    this.element.innerHTML = `
      <div class="flex items-start gap-3">
        <div class="w-8 h-8 bg-gray-300 rounded"></div>
        <div class="flex-1 space-y-2">
          <div class="h-4 bg-gray-300 rounded w-3/4"></div>
          <div class="h-3 bg-gray-300 rounded w-1/2"></div>
        </div>
      </div>
    `;
  }

  attachEvents() {
    const editBtn = this.element.querySelector('.edit-btn');
    const deleteBtn = this.element.querySelector('.delete-btn');
    const checkbox = this.element.querySelector('input[type="checkbox"]');

    if (editBtn) {
      editBtn.addEventListener('click', () => {
        if (this.options.onEdit) {
          this.options.onEdit(this.options.flow.id);
        } else {
          this.defaultEditHandler(this.options.flow.id);
        }
      });
    }

    if (deleteBtn) {
      deleteBtn.addEventListener('click', () => {
        if (this.options.onDelete) {
          this.options.onDelete(this.options.flow.id);
        } else {
          this.defaultDeleteHandler(this.options.flow.id);
        }
      });
    }

    if (checkbox) {
      checkbox.addEventListener('change', (e) => {
        if (this.options.onSelect) {
          this.options.onSelect(this.options.flow.id, e.target.checked);
        }

        const event = new CustomEvent('flow:select', {
          detail: {
            flowId: this.options.flow.id,
            selected: e.target.checked
          }
        });
        document.dispatchEvent(event);
      });
    }

    if (this.options.selectable) {
      this.element.addEventListener('click', (e) => {
        if (e.target.type !== 'checkbox' && !e.target.closest('button')) {
          const checkbox = this.element.querySelector('input[type="checkbox"]');
          if (checkbox) {
            checkbox.checked = !checkbox.checked;
            checkbox.dispatchEvent(new Event('change'));
          }
        }
      });
    }
  }

  defaultEditHandler(flowId) {
    window.location.href = `/flows/${flowId}/edit`;
  }

  defaultDeleteHandler(flowId) {
    if (confirm('정말로 이 플로우를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) {
      fetch(`/api/v1/flows/${flowId}`, {
        method: 'DELETE',
        credentials: 'include'
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          this.showSuccessMessage('플로우가 삭제되었습니다.');
          this.animateRemoval();
        } else {
          throw new Error(data.message || '삭제에 실패했습니다.');
        }
      })
      .catch(error => {
        this.showErrorMessage(error.message);
      });
    }
  }

  animateRemoval() {
    this.element.style.transition = 'all 0.3s ease-out';
    this.element.style.opacity = '0';
    this.element.style.transform = 'scale(0.95)';

    setTimeout(() => {
      if (this.element.parentNode) {
        this.element.parentNode.removeChild(this.element);
      }
    }, 300);
  }

  formatTimeAgo(timestamp) {
    const now = new Date();
    const time = new Date(timestamp);
    const diffInMs = now - time;
    const diffInMins = Math.floor(diffInMs / 60000);
    const diffInHours = Math.floor(diffInMins / 60);
    const diffInDays = Math.floor(diffInHours / 24);

    if (diffInDays > 0) {
      return `${diffInDays}일 전`;
    } else if (diffInHours > 0) {
      return `${diffInHours}시간 전`;
    } else if (diffInMins > 0) {
      return `${diffInMins}분 전`;
    } else {
      return '방금 전';
    }
  }

  showSuccessMessage(message) {
    if (window.showSuccessMessage) {
      window.showSuccessMessage(message);
    } else {
      alert(message);
    }
  }

  showErrorMessage(message) {
    if (window.showErrorMessage) {
      window.showErrorMessage(message);
    } else {
      alert(message);
    }
  }

  updateFlow(newFlow) {
    this.options.flow = newFlow;
    this.updateElement();
  }

  updateStatus(newStatus) {
    if (this.options.flow) {
      this.options.flow.status = newStatus;
      this.updateElement();
    }
  }

  setSelected(selected) {
    const checkbox = this.element.querySelector('input[type="checkbox"]');
    if (checkbox) {
      checkbox.checked = selected;
    }
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
    return new FlowCard(options);
  }

  static createFromElement(element) {
    const flowId = element.dataset.flowId;
    const flowData = JSON.parse(element.dataset.flow || '{}');

    const card = new FlowCard({
      flow: { id: flowId, ...flowData },
      showActions: element.dataset.showActions !== 'false',
      compact: element.dataset.compact === 'true',
      selectable: element.dataset.selectable === 'true'
    });

    element.parentNode.replaceChild(card.element, element);
    return card;
  }
}

// CSS 스타일 추가
if (!document.querySelector('#flow-card-styles')) {
  const style = document.createElement('style');
  style.id = 'flow-card-styles';
  style.textContent = `
    .line-clamp-2 {
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .flow-card:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    }

    .flow-card .module-flow {
      scrollbar-width: thin;
      scrollbar-color: #cbd5e0 transparent;
    }

    .flow-card .module-flow::-webkit-scrollbar {
      height: 4px;
    }

    .flow-card .module-flow::-webkit-scrollbar-track {
      background: transparent;
    }

    .flow-card .module-flow::-webkit-scrollbar-thumb {
      background-color: #cbd5e0;
      border-radius: 2px;
    }
  `;
  document.head.appendChild(style);
}

// DOM이 로드된 후 자동 초기화
document.addEventListener('DOMContentLoaded', () => {
  const elements = document.querySelectorAll('[data-flow-card]');
  elements.forEach(element => {
    FlowCard.createFromElement(element);
  });
});

// 전역으로 사용할 수 있도록 window 객체에 추가
window.FlowCard = FlowCard;