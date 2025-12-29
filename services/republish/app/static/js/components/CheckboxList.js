/**
 * CheckboxList 컴포넌트
 * 다중 선택이 가능한 체크박스 목록
 */

class CheckboxList {
  constructor(options) {
    this.options = {
      id: this.generateId(),
      title: '항목 선택',
      items: [],
      name: 'selected_items',
      showSearch: true,
      showSelectAll: true,
      compact: false,
      maxHeight: '16rem', // 64 * 0.25rem = 16rem
      onChange: null,
      onSelect: null,
      ...options
    };

    this.element = null;
    this.selectedItems = new Set();
    this.filteredItems = new Set();
    this.init();
  }

  generateId() {
    return 'checkboxList-' + Math.random().toString(36).substr(2, 9);
  }

  init() {
    this.createElement();
    this.attachEvents();
    this.updateSelectionState();
  }

  createElement() {
    this.element = document.createElement('div');
    this.element.className = 'checkbox-list-container';
    this.element.setAttribute('data-list-id', this.options.id);

    this.element.innerHTML = this.createHTML();
  }

  createHTML() {
    const { title, items, showSearch, showSelectAll } = this.options;

    return `
      <!-- 헤더 -->
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-semibold text-gray-900">${title}</h3>
        <span class="text-sm text-gray-500">
          <span class="selected-count">0</span>개 선택됨
        </span>
      </div>

      <!-- 검색 및 전체 선택 -->
      <div class="mb-4 space-y-3">
        ${showSearch ? this.createSearchHTML() : ''}
        ${showSelectAll ? this.createSelectAllHTML() : ''}
      </div>

      <!-- 체크박스 목록 -->
      <div class="checkbox-list max-h-64 overflow-y-auto border border-gray-200 rounded-lg"
           style="max-height: ${this.options.maxHeight}">
        ${this.createItemsHTML()}
      </div>

      <!-- 하단 정보 -->
      <div class="mt-3 flex items-center justify-between text-xs text-gray-500">
        <span class="total-count">전체 ${items.length}개</span>
        <span class="filtered-info" style="display: none;">필터된 결과</span>
      </div>
    `;
  }

  createSearchHTML() {
    return `
      <div class="relative">
        <input type="text"
               class="search-input w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
               placeholder="검색...">
        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
          </svg>
        </div>
      </div>
    `;
  }

  createSelectAllHTML() {
    return `
      <div class="flex items-center justify-between">
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" class="select-all-checkbox w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500">
          <span class="text-sm font-medium text-gray-700">전체 선택</span>
        </label>
        <button type="button" class="clear-selection-btn text-sm text-gray-500 hover:text-gray-700">
          선택 해제
        </button>
      </div>
    `;
  }

  createItemsHTML() {
    const { items, name, compact } = this.options;

    if (!items || items.length === 0) {
      return this.createEmptyStateHTML();
    }

    return items.map(item => this.createItemHTML(item, name, compact)).join('');
  }

  createItemHTML(item, name, compact) {
    const searchable = `${item.name?.toLowerCase() || ''} ${item.description?.toLowerCase() || ''}`;

    return `
      <label class="checkbox-item flex items-center p-3 hover:bg-gray-50 border-b border-gray-100 last:border-b-0 cursor-pointer"
             data-item-id="${item.id}"
             data-item-name="${item.name || ''}"
             data-searchable="${searchable}">

        <input type="checkbox"
               name="${name}"
               value="${item.id}"
               class="item-checkbox w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 mr-3"
               ${item.checked ? 'checked' : ''}>

        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            ${item.icon ? `<span class="text-lg">${item.icon}</span>` : ''}
            <span class="font-medium text-gray-900 truncate">${item.name || ''}</span>
            ${item.badge ? `<span class="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">${item.badge}</span>` : ''}
          </div>

          ${item.description && !compact ?
            `<p class="text-sm text-gray-500 mt-1 truncate">${item.description}</p>` : ''}
        </div>

        ${item.status ? this.createStatusBadgeHTML(item.status) : ''}
      </label>
    `;
  }

  createStatusBadgeHTML(status) {
    const statusColors = {
      active: 'bg-green-100 text-green-800',
      inactive: 'bg-gray-100 text-gray-600',
      paused: 'bg-yellow-100 text-yellow-800',
      error: 'bg-red-100 text-red-800'
    };

    const colorClass = statusColors[status] || statusColors.inactive;

    return `
      <div class="ml-2">
        <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${colorClass}">
          ${status}
        </span>
      </div>
    `;
  }

  createEmptyStateHTML() {
    return `
      <div class="p-8 text-center text-gray-500">
        <svg class="w-12 h-12 mx-auto mb-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
        </svg>
        <p class="text-lg font-medium">항목이 없습니다</p>
        <p class="text-sm">선택할 수 있는 항목이 없습니다.</p>
      </div>
    `;
  }

  attachEvents() {
    const searchInput = this.element.querySelector('.search-input');
    const selectAllCheckbox = this.element.querySelector('.select-all-checkbox');
    const clearButton = this.element.querySelector('.clear-selection-btn');

    // 검색 기능
    if (searchInput) {
      searchInput.addEventListener('input', (e) => this.handleSearch(e));
    }

    // 전체 선택/해제
    if (selectAllCheckbox) {
      selectAllCheckbox.addEventListener('change', (e) => this.handleSelectAll(e));
    }

    // 선택 해제
    if (clearButton) {
      clearButton.addEventListener('click', () => this.clearSelection());
    }

    // 개별 체크박스 이벤트
    this.attachItemEvents();
  }

  attachItemEvents() {
    const itemCheckboxes = this.element.querySelectorAll('.item-checkbox');
    itemCheckboxes.forEach(checkbox => {
      checkbox.addEventListener('change', (e) => this.handleItemChange(e));
    });
  }

  handleSearch(e) {
    const query = e.target.value.toLowerCase().trim();
    const items = this.element.querySelectorAll('.checkbox-item');
    let visibleCount = 0;

    this.filteredItems.clear();

    items.forEach(item => {
      const searchable = item.dataset.searchable || '';
      const isVisible = !query || searchable.includes(query);
      item.style.display = isVisible ? '' : 'none';

      if (isVisible) {
        visibleCount++;
        this.filteredItems.add(item.dataset.itemId);
      }
    });

    const filteredInfo = this.element.querySelector('.filtered-info');
    filteredInfo.style.display = query ? 'block' : 'none';
    filteredInfo.textContent = `${visibleCount}개 항목이 검색됨`;

    this.updateSelectionState();
  }

  handleSelectAll(e) {
    const isChecked = e.target.checked;
    const visibleCheckboxes = this.getVisibleCheckboxes();

    visibleCheckboxes.forEach(checkbox => {
      checkbox.checked = isChecked;
      const itemId = checkbox.value;

      if (isChecked) {
        this.selectedItems.add(itemId);
      } else {
        this.selectedItems.delete(itemId);
      }
    });

    this.updateSelectionState();
    this.triggerChangeEvent();
  }

  handleItemChange(e) {
    const checkbox = e.target;
    const itemId = checkbox.value;

    if (checkbox.checked) {
      this.selectedItems.add(itemId);
    } else {
      this.selectedItems.delete(itemId);
    }

    this.updateSelectionState();
    this.triggerChangeEvent();

    if (this.options.onSelect) {
      this.options.onSelect(itemId, checkbox.checked, this.getItemData(itemId));
    }
  }

  getVisibleCheckboxes() {
    const checkboxes = this.element.querySelectorAll('.item-checkbox');
    return Array.from(checkboxes).filter(cb => {
      const item = cb.closest('.checkbox-item');
      return !item.style.display || item.style.display !== 'none';
    });
  }

  updateSelectionState() {
    const visibleCheckboxes = this.getVisibleCheckboxes();
    const checkedCount = visibleCheckboxes.filter(cb => cb.checked).length;
    const totalVisible = visibleCheckboxes.length;

    // 선택 개수 업데이트
    const selectedCountSpan = this.element.querySelector('.selected-count');
    selectedCountSpan.textContent = this.selectedItems.size;

    // 전체 선택 체크박스 상태 업데이트
    const selectAllCheckbox = this.element.querySelector('.select-all-checkbox');
    if (selectAllCheckbox && totalVisible > 0) {
      selectAllCheckbox.checked = checkedCount === totalVisible;
      selectAllCheckbox.indeterminate = checkedCount > 0 && checkedCount < totalVisible;
    }
  }

  triggerChangeEvent() {
    const selectedData = this.getSelectedItems();

    if (this.options.onChange) {
      this.options.onChange(selectedData, this.selectedItems);
    }

    const event = new CustomEvent('checkboxList:change', {
      detail: {
        listId: this.options.id,
        selectedItems: selectedData,
        selectedCount: this.selectedItems.size,
        selectedIds: Array.from(this.selectedItems)
      }
    });

    this.element.dispatchEvent(event);
  }

  // 공용 메서드들
  getSelectedItems() {
    const result = [];
    this.selectedItems.forEach(id => {
      const item = this.getItemData(id);
      if (item) result.push(item);
    });
    return result;
  }

  getSelectedIds() {
    return Array.from(this.selectedItems);
  }

  getItemData(itemId) {
    const item = this.element.querySelector(`[data-item-id="${itemId}"]`);
    if (!item) return null;

    return {
      id: itemId,
      name: item.dataset.itemName,
      element: item,
      checkbox: item.querySelector('.item-checkbox')
    };
  }

  selectItems(itemIds) {
    const checkboxes = this.element.querySelectorAll('.item-checkbox');
    checkboxes.forEach(checkbox => {
      const shouldSelect = itemIds.includes(checkbox.value);
      checkbox.checked = shouldSelect;

      if (shouldSelect) {
        this.selectedItems.add(checkbox.value);
      } else {
        this.selectedItems.delete(checkbox.value);
      }
    });

    this.updateSelectionState();
    this.triggerChangeEvent();
  }

  selectAll() {
    const checkboxes = this.element.querySelectorAll('.item-checkbox');
    checkboxes.forEach(checkbox => {
      checkbox.checked = true;
      this.selectedItems.add(checkbox.value);
    });

    this.updateSelectionState();
    this.triggerChangeEvent();
  }

  clearSelection() {
    const checkboxes = this.element.querySelectorAll('.item-checkbox');
    checkboxes.forEach(checkbox => {
      checkbox.checked = false;
    });

    this.selectedItems.clear();
    this.updateSelectionState();
    this.triggerChangeEvent();
  }

  filter(query) {
    const searchInput = this.element.querySelector('.search-input');
    if (searchInput) {
      searchInput.value = query;
      searchInput.dispatchEvent(new Event('input'));
    }
  }

  updateItems(newItems) {
    this.options.items = newItems;
    const listContainer = this.element.querySelector('.checkbox-list');
    listContainer.innerHTML = this.createItemsHTML();

    this.attachItemEvents();
    this.updateSelectionState();
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
    return new CheckboxList(options);
  }

  static createFromElement(element) {
    const listId = element.dataset.listId || element.id;
    const items = JSON.parse(element.dataset.items || '[]');

    const checkboxList = new CheckboxList({
      id: listId,
      items: items,
      showSearch: element.dataset.showSearch !== 'false',
      showSelectAll: element.dataset.showSelectAll !== 'false',
      compact: element.dataset.compact === 'true'
    });

    element.parentNode.replaceChild(checkboxList.element, element);
    return checkboxList;
  }
}

// CSS 스타일 추가
if (!document.querySelector('#checkbox-list-styles')) {
  const style = document.createElement('style');
  style.id = 'checkbox-list-styles';
  style.textContent = `
    .checkbox-list {
      scrollbar-width: thin;
      scrollbar-color: #cbd5e0 transparent;
    }

    .checkbox-list::-webkit-scrollbar {
      width: 6px;
    }

    .checkbox-list::-webkit-scrollbar-track {
      background: transparent;
    }

    .checkbox-list::-webkit-scrollbar-thumb {
      background-color: #cbd5e0;
      border-radius: 3px;
    }

    .checkbox-item:hover {
      background-color: #f9fafb;
      transition: background-color 0.2s ease;
    }

    .checkbox-list .search-input:focus {
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }

    .checkbox-item:has(.item-checkbox:checked) {
      background-color: #eff6ff;
      border-color: #dbeafe;
    }

    .checkbox-list .checkbox-item:last-child {
      border-bottom: none !important;
    }
  `;
  document.head.appendChild(style);
}

// DOM이 로드된 후 자동 초기화
document.addEventListener('DOMContentLoaded', () => {
  const elements = document.querySelectorAll('[data-checkbox-list]');
  elements.forEach(element => {
    CheckboxList.createFromElement(element);
  });
});

// 전역으로 사용할 수 있도록 window 객체에 추가
window.CheckboxList = CheckboxList;