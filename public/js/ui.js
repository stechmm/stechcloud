// UI Components & View Helpers
const UI = {
  formatBytes(bytes, decimals = 2) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  },

  formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  },

  getCategoryIcon(category, isDir) {
    if (isDir) return '<i class="fa-solid fa-folder file-icon-large file-icon-folder"></i>';
    switch (category) {
      case 'photo': return '<i class="fa-solid fa-image file-icon-large" style="color:#38bdf8;"></i>';
      case 'video': return '<i class="fa-solid fa-film file-icon-large file-icon-video"></i>';
      case 'audio': return '<i class="fa-solid fa-music file-icon-large file-icon-audio"></i>';
      case 'document': return '<i class="fa-solid fa-file-lines file-icon-large file-icon-document"></i>';
      case 'archive': return '<i class="fa-solid fa-file-zipper file-icon-large file-icon-archive"></i>';
      case 'code': return '<i class="fa-solid fa-file-code file-icon-large file-icon-code"></i>';
      default: return '<i class="fa-solid fa-file file-icon-large" style="color:#94a3b8;"></i>';
    }
  },

  showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'toast';
    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle text-success';
    if (type === 'error') icon = 'fa-exclamation-triangle text-danger';

    toast.innerHTML = `<i class="fa-solid ${icon}"></i><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  },

  renderBreadcrumbs(currentPath, onNavigate) {
    const container = document.getElementById('breadcrumbs');
    if (!container) return;
    container.innerHTML = '';

    const rootBtn = document.createElement('span');
    rootBtn.className = `breadcrumb-item ${!currentPath ? 'active' : ''}`;
    rootBtn.innerHTML = '<i class="fa-solid fa-cloud me-1"></i> S-Tech Cloud';
    rootBtn.onclick = () => onNavigate('');
    container.appendChild(rootBtn);

    if (!currentPath) return;

    const parts = currentPath.split('/').filter(Boolean);
    let accum = '';
    parts.forEach((part, index) => {
      accum += (accum ? '/' : '') + part;
      const targetPath = accum;
      const isLast = index === parts.length - 1;

      const sep = document.createElement('span');
      sep.className = 'breadcrumb-separator';
      sep.innerHTML = '<i class="fa-solid fa-chevron-right"></i>';
      container.appendChild(sep);

      const partBtn = document.createElement('span');
      partBtn.className = `breadcrumb-item ${isLast ? 'active' : ''}`;
      partBtn.textContent = part;
      if (!isLast) {
        partBtn.onclick = () => onNavigate(targetPath);
      }
      container.appendChild(partBtn);
    });
  },

  renderFileGrid(items, options = {}) {
    const { onOpen, onSelect, onStar, isTrash, selectedPaths = [] } = options;
    const container = document.getElementById('file-container');
    container.innerHTML = '';

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fa-regular fa-folder-open empty-icon"></i>
          <h3>No files or folders here</h3>
          <p class="text-dim">Drag and drop files here or click Upload to get started</p>
        </div>
      `;
      return;
    }

    const grid = document.createElement('div');
    grid.className = 'file-grid';

    items.forEach(item => {
      const card = document.createElement('div');
      const itemKey = isTrash ? item.id : item.path;
      const isSelected = selectedPaths.includes(itemKey);
      card.className = `file-card ${isSelected ? 'selected' : ''}`;

      let previewArea = '';
      if (!item.isDirectory && item.category === 'photo') {
        const previewUrl = API.getPreviewUrl(item.path);
        previewArea = `<img src="${previewUrl}" class="file-thumbnail" loading="lazy" alt="${item.name}" />`;
      } else {
        previewArea = UI.getCategoryIcon(item.category, item.isDirectory);
      }

      const starBtn = (!isTrash) ? `
        <button class="card-star-btn ${item.isStarred ? 'starred' : ''}" title="${item.isStarred ? 'Unstar' : 'Star'}" data-path="${item.path}">
          <i class="fa-${item.isStarred ? 'solid' : 'regular'} fa-star"></i>
        </button>
      ` : '';

      card.innerHTML = `
        <div class="file-preview-area">
          ${previewArea}
        </div>
        ${starBtn}
        <div class="file-meta">
          <div class="file-name" title="${item.name}">${item.name}</div>
          <div class="file-info">
            <span>${item.isDirectory ? 'Folder' : UI.formatBytes(item.size)}</span>
            <span>${UI.formatDate(item.modifiedAt || item.deletedAt)}</span>
          </div>
        </div>
      `;

      // Event handlers
      card.addEventListener('click', (e) => {
        if (e.target.closest('.card-star-btn')) {
          e.stopPropagation();
          onStar && onStar(item.path);
          return;
        }
        if (e.ctrlKey || e.metaKey || options.selectMode) {
          onSelect && onSelect(itemKey);
        } else {
          onOpen && onOpen(item);
        }
      });

      card.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        onSelect && onSelect(itemKey, true);
        UI.showContextMenu(e.pageX, e.pageY, item, options);
      });

      grid.appendChild(card);
    });

    container.appendChild(grid);
  },

  renderFileTable(items, options = {}) {
    const { onOpen, onSelect, onStar, isTrash, selectedPaths = [] } = options;
    const container = document.getElementById('file-container');
    container.innerHTML = '';

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fa-regular fa-folder-open empty-icon"></i>
          <h3>No files found</h3>
        </div>
      `;
      return;
    }

    const tableWrapper = document.createElement('div');
    tableWrapper.className = 'file-table-container';

    let rowsHtml = '';
    items.forEach(item => {
      const itemKey = isTrash ? item.id : item.path;
      const isSelected = selectedPaths.includes(itemKey);
      let icon = item.isDirectory ? '<i class="fa-solid fa-folder text-warning me-2"></i>' : '<i class="fa-regular fa-file text-primary me-2"></i>';
      if (item.category === 'photo') icon = '<i class="fa-regular fa-image text-info me-2"></i>';
      if (item.category === 'video') icon = '<i class="fa-solid fa-film text-danger me-2"></i>';

      rowsHtml += `
        <tr data-key="${itemKey}" class="${isSelected ? 'selected' : ''}">
          <td style="width: 40px;">
            <input type="checkbox" class="file-checkbox" ${isSelected ? 'checked' : ''} />
          </td>
          <td>
            <div class="table-file-name-cell">
              ${icon}
              <span class="file-name-text">${item.name}</span>
            </div>
          </td>
          <td>${item.isDirectory ? '--' : UI.formatBytes(item.size)}</td>
          <td>${UI.formatDate(item.modifiedAt || item.deletedAt)}</td>
          <td style="text-align: right;">
            ${!isTrash ? `
              <button class="icon-btn btn-sm star-action" title="Star" data-path="${item.path}">
                <i class="fa-${item.isStarred ? 'solid text-warning' : 'regular'} fa-star"></i>
              </button>
            ` : ''}
          </td>
        </tr>
      `;
    });

    tableWrapper.innerHTML = `
      <table class="file-table">
        <thead>
          <tr>
            <th style="width: 40px;"><input type="checkbox" id="select-all-checkbox" /></th>
            <th>Name</th>
            <th>Size</th>
            <th>Modified</th>
            <th style="text-align: right;">Actions</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    `;

    tableWrapper.querySelectorAll('tbody tr').forEach((tr, i) => {
      const item = items[i];
      const itemKey = isTrash ? item.id : item.path;

      tr.addEventListener('click', (e) => {
        if (e.target.closest('.star-action')) {
          onStar && onStar(item.path);
          return;
        }
        if (e.target.closest('.file-checkbox') || e.ctrlKey || e.metaKey) {
          onSelect && onSelect(itemKey);
        } else {
          onOpen && onOpen(item);
        }
      });
    });

    container.appendChild(tableWrapper);
  },

  showContextMenu(x, y, item, options) {
    let menu = document.getElementById('context-menu');
    if (menu) menu.remove();

    menu = document.createElement('div');
    menu.id = 'context-menu';
    menu.style.position = 'fixed';
    menu.style.left = `${Math.min(x, window.innerWidth - 200)}px`;
    menu.style.top = `${Math.min(y, window.innerHeight - 250)}px`;
    menu.style.backgroundColor = 'var(--bg-surface-elevated)';
    menu.style.border = '1px solid var(--border-color)';
    menu.style.borderRadius = 'var(--radius-md)';
    menu.style.boxShadow = 'var(--shadow-xl)';
    menu.style.padding = '0.5rem';
    menu.style.zIndex = '500';
    menu.style.minWidth = '180px';

    if (options.isTrash) {
      menu.innerHTML = `
        <button class="nav-item" id="ctx-restore"><i class="fa-solid fa-rotate-left"></i> Restore</button>
        <button class="nav-item text-danger" id="ctx-purge"><i class="fa-solid fa-trash-can"></i> Delete Forever</button>
      `;
      menu.querySelector('#ctx-restore').onclick = () => { menu.remove(); options.onRestore([item.id]); };
      menu.querySelector('#ctx-purge').onclick = () => { menu.remove(); options.onPurge([item.id]); };
    } else {
      menu.innerHTML = `
        <button class="nav-item" id="ctx-open"><i class="fa-solid fa-arrow-up-right-from-square"></i> Open / Preview</button>
        <button class="nav-item" id="ctx-download"><i class="fa-solid fa-download"></i> Download</button>
        <button class="nav-item" id="ctx-share"><i class="fa-solid fa-share-nodes"></i> Share Link</button>
        <button class="nav-item" id="ctx-rename"><i class="fa-solid fa-pen"></i> Rename</button>
        <button class="nav-item" id="ctx-star"><i class="fa-solid fa-star"></i> ${item.isStarred ? 'Unstar' : 'Star'}</button>
        <div style="height:1px; background:var(--border-color); margin:0.25rem 0;"></div>
        <button class="nav-item text-danger" id="ctx-delete"><i class="fa-solid fa-trash"></i> Move to Trash</button>
      `;
      menu.querySelector('#ctx-open').onclick = () => { menu.remove(); options.onOpen(item); };
      menu.querySelector('#ctx-download').onclick = () => { menu.remove(); window.open(API.getDownloadUrl(item.path), '_blank'); };
      menu.querySelector('#ctx-share').onclick = () => { menu.remove(); options.onShare(item); };
      menu.querySelector('#ctx-rename').onclick = () => { menu.remove(); options.onRename(item); };
      menu.querySelector('#ctx-star').onclick = () => { menu.remove(); options.onStar(item.path); };
      menu.querySelector('#ctx-delete').onclick = () => { menu.remove(); options.onDelete([item.path]); };
    }

    document.body.appendChild(menu);

    const closeCtx = (e) => {
      if (!menu.contains(e.target)) {
        menu.remove();
        document.removeEventListener('click', closeCtx);
      }
    };
    setTimeout(() => document.addEventListener('click', closeCtx), 10);
  },

  openPreview(item) {
    const modal = document.getElementById('preview-modal');
    const content = document.getElementById('preview-content');
    const title = document.getElementById('preview-title');
    const downloadBtn = document.getElementById('preview-download-btn');

    title.textContent = item.name;
    downloadBtn.onclick = () => window.open(API.getDownloadUrl(item.path), '_blank');
    content.innerHTML = '<div class="spinner-border text-primary"></div>';
    modal.classList.add('show');

    const previewUrl = API.getPreviewUrl(item.path);

    if (item.category === 'photo') {
      content.innerHTML = `<img src="${previewUrl}" class="preview-img" alt="${item.name}" />`;
    } else if (item.category === 'video') {
      content.innerHTML = `
        <video controls autoplay playsinline class="preview-video">
          <source src="${previewUrl}" type="${item.mimeType || 'video/mp4'}">
          Your browser does not support the video tag.
        </video>
      `;
    } else if (item.category === 'audio') {
      content.innerHTML = `
        <div class="preview-audio-container">
          <i class="fa-solid fa-music fa-4x text-primary"></i>
          <h4>${item.name}</h4>
          <audio controls autoplay style="width: 100%; max-width: 400px;">
            <source src="${previewUrl}" type="${item.mimeType || 'audio/mp3'}">
          </audio>
        </div>
      `;
    } else if (item.category === 'code' || item.category === 'document' && item.name.endsWith('.txt') || item.name.endsWith('.md')) {
      fetch(previewUrl)
        .then(res => res.text())
        .then(text => {
          content.innerHTML = `<pre class="preview-code">${UI.escapeHtml(text)}</pre>`;
        })
        .catch(err => {
          content.innerHTML = `<p class="text-danger">Failed to read file content: ${err.message}</p>`;
        });
    } else if (item.name.endsWith('.pdf')) {
      content.innerHTML = `<iframe src="${previewUrl}" style="width:100%; height:80vh; border:none; border-radius:8px;"></iframe>`;
    } else {
      content.innerHTML = `
        <div class="text-center">
          <i class="fa-solid fa-file fa-4x text-muted mb-3"></i>
          <h3>Preview not available</h3>
          <p class="text-dim">You can download this file to view on your device.</p>
          <a href="${API.getDownloadUrl(item.path)}" class="btn-primary mt-3" style="display:inline-flex;">
            <i class="fa-solid fa-download"></i> Download File
          </a>
        </div>
      `;
    }
  },

  escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
};
