// Main Application Controller
let state = {
  currentPath: '',
  currentFilter: 'all', // all, photos, videos, audio, docs, starred, recent, trash
  searchQuery: '',
  viewMode: localStorage.getItem('cloud_view_mode') || 'grid', // grid or list
  items: [],
  selectedKeys: [],
  theme: localStorage.getItem('cloud_theme') || 'dark'
};

document.addEventListener('DOMContentLoaded', async () => {
  // Apply initial theme
  document.documentElement.setAttribute('data-theme', state.theme);

  // Check auth
  const isAuthed = await API.verifyAuth();
  if (!isAuthed) {
    showLoginModal();
  } else {
    initApp();
  }

  window.addEventListener('auth-required', () => {
    showLoginModal();
  });
});

function initApp() {
  hideLoginModal();
  setupEventListeners();
  loadFiles();
  updateStorageStats();
}

async function loadFiles() {
  try {
    const isTrash = state.currentFilter === 'trash';
    const data = await API.getFiles(state.currentPath, state.currentFilter, state.searchQuery);
    
    if (data.success) {
      state.items = data.items || [];
      state.selectedKeys = [];
      updateSelectionBar();

      // Render Breadcrumbs
      if (!isTrash && !state.searchQuery && ['all', 'starred', 'recent'].includes(state.currentFilter)) {
        UI.renderBreadcrumbs(state.currentPath, (newPath) => {
          state.currentPath = newPath;
          state.currentFilter = 'all';
          state.searchQuery = '';
          loadFiles();
        });
      } else {
        const titleContainer = document.getElementById('breadcrumbs');
        let filterTitle = state.currentFilter.toUpperCase();
        if (state.searchQuery) filterTitle = `Search: "${state.searchQuery}"`;
        titleContainer.innerHTML = `<span class="breadcrumb-item active"><i class="fa-solid fa-folder-tree me-1"></i> ${filterTitle}</span>`;
      }

      // Render Grid or Table
      renderCurrentView();
    }
  } catch (err) {
    UI.showToast(err.message || 'Failed to load files', 'error');
  }
}

function renderCurrentView() {
  const isTrash = state.currentFilter === 'trash';
  const renderOptions = {
    isTrash,
    selectedPaths: state.selectedKeys,
    onOpen: (item) => {
      if (item.isDirectory) {
        state.currentPath = item.path;
        state.currentFilter = 'all';
        state.searchQuery = '';
        loadFiles();
      } else {
        UI.openPreview(item);
      }
    },
    onSelect: (key) => {
      const idx = state.selectedKeys.indexOf(key);
      if (idx >= 0) state.selectedKeys.splice(idx, 1);
      else state.selectedKeys.push(key);
      updateSelectionBar();
      renderCurrentView();
    },
    onStar: async (path) => {
      const res = await API.toggleStar(path);
      if (res.success) {
        UI.showToast(res.isStarred ? 'Added to Starred' : 'Removed from Starred', 'info');
        loadFiles();
      }
    },
    onShare: (item) => openShareModal(item),
    onRename: (item) => openRenameModal(item),
    onDelete: async (paths) => {
      if (confirm(`Move ${paths.length} item(s) to Trash?`)) {
        const res = await API.deleteItems(paths);
        if (res.success) {
          UI.showToast(res.message, 'success');
          loadFiles();
          updateStorageStats();
        }
      }
    },
    onRestore: async (ids) => {
      const res = await API.restoreTrash(ids);
      if (res.success) {
        UI.showToast(res.message, 'success');
        loadFiles();
        updateStorageStats();
      }
    },
    onPurge: async (ids) => {
      if (confirm(`Permanently delete ${ids.length} item(s)? This cannot be undone!`)) {
        const res = await API.purgeTrash(ids);
        if (res.success) {
          UI.showToast(res.message, 'success');
          loadFiles();
          updateStorageStats();
        }
      }
    }
  };

  if (state.viewMode === 'grid') {
    UI.renderFileGrid(state.items, renderOptions);
  } else {
    UI.renderFileTable(state.items, renderOptions);
  }
}

function updateSelectionBar() {
  const bar = document.getElementById('selection-bar');
  const countSpan = document.getElementById('selection-count');
  const isTrash = state.currentFilter === 'trash';

  if (!bar) return;

  if (state.selectedKeys.length > 0) {
    bar.classList.add('show');
    countSpan.textContent = `${state.selectedKeys.length} selected`;

    const trashActions = document.getElementById('selection-trash-actions');
    const normalActions = document.getElementById('selection-normal-actions');

    if (isTrash) {
      trashActions.style.display = 'flex';
      normalActions.style.display = 'none';
    } else {
      trashActions.style.display = 'none';
      normalActions.style.display = 'flex';
    }
  } else {
    bar.classList.remove('show');
  }
}

async function updateStorageStats() {
  try {
    const res = await API.getStats();
    if (res.success) {
      const stats = res.stats;
      const fillEl = document.getElementById('storage-fill');
      const textEl = document.getElementById('storage-text');
      
      const usedFormatted = UI.formatBytes(stats.totalSizeBytes);
      textEl.textContent = `${usedFormatted} Used`;

      // Visual indicator for 100GB reference (or auto percentage)
      const percent = Math.min(100, Math.max(5, (stats.totalSizeBytes / (50 * 1024 * 1024 * 1024)) * 100));
      fillEl.style.width = `${percent}%`;
    }
  } catch (err) {
    console.error('Stats error:', err);
  }
}

// Event Listeners Setup
function setupEventListeners() {
  // Navigation tabs (desktop and mobile)
  const navItems = document.querySelectorAll('.nav-item[data-filter], .bottom-nav-item[data-filter]');
  navItems.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      navItems.forEach(n => n.classList.remove('active'));
      const filter = btn.getAttribute('data-filter');
      document.querySelectorAll(`[data-filter="${filter}"]`).forEach(el => el.classList.add('active'));

      state.currentFilter = filter;
      state.searchQuery = '';
      if (filter === 'all') state.currentPath = '';
      loadFiles();
    });
  });

  // Search input
  const searchInput = document.getElementById('search-input');
  let searchTimeout;
  searchInput.addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      state.searchQuery = e.target.value;
      loadFiles();
    }, 300);
  });

  // View mode toggle
  const viewToggleBtn = document.getElementById('view-toggle-btn');
  viewToggleBtn.addEventListener('click', () => {
    state.viewMode = state.viewMode === 'grid' ? 'list' : 'grid';
    localStorage.setItem('cloud_view_mode', state.viewMode);
    viewToggleBtn.innerHTML = state.viewMode === 'grid' ? '<i class="fa-solid fa-list"></i>' : '<i class="fa-solid fa-grip"></i>';
    renderCurrentView();
  });

  // Theme toggle
  const themeToggleBtn = document.getElementById('theme-toggle-btn');
  themeToggleBtn.addEventListener('click', () => {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('cloud_theme', state.theme);
    document.documentElement.setAttribute('data-theme', state.theme);
    themeToggleBtn.innerHTML = state.theme === 'dark' ? '<i class="fa-solid fa-sun"></i>' : '<i class="fa-solid fa-moon"></i>';
  });

  // New Folder button
  const newFolderBtn = document.getElementById('new-folder-btn');
  newFolderBtn.addEventListener('click', () => {
    document.getElementById('new-folder-input').value = '';
    document.getElementById('new-folder-modal').classList.add('show');
  });

  // Upload buttons
  const fileUploadInput = document.getElementById('file-upload-input');
  const folderUploadInput = document.getElementById('folder-upload-input');

  document.getElementById('upload-file-btn').addEventListener('click', () => fileUploadInput.click());
  const uploadFolderBtn = document.getElementById('upload-folder-btn');
  if (uploadFolderBtn) uploadFolderBtn.addEventListener('click', () => folderUploadInput.click());

  fileUploadInput.addEventListener('change', (e) => handleUpload(e.target.files));
  folderUploadInput.addEventListener('change', (e) => handleUpload(e.target.files));

  // Drag and Drop
  const dropzone = document.getElementById('dropzone-overlay');
  window.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('active');
  });

  dropzone.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dropzone.classList.remove('active');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('active');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleUpload(e.dataTransfer.files);
    }
  });

  // Batch actions
  document.getElementById('batch-download-btn')?.addEventListener('click', () => {
    window.open(API.getBatchDownloadUrl(state.selectedKeys), '_blank');
  });

  document.getElementById('batch-delete-btn')?.addEventListener('click', async () => {
    if (confirm(`Move ${state.selectedKeys.length} items to Trash?`)) {
      const res = await API.deleteItems(state.selectedKeys);
      if (res.success) {
        UI.showToast(res.message, 'success');
        loadFiles();
        updateStorageStats();
      }
    }
  });

  document.getElementById('batch-restore-btn')?.addEventListener('click', async () => {
    const res = await API.restoreTrash(state.selectedKeys);
    if (res.success) {
      UI.showToast(res.message, 'success');
      loadFiles();
      updateStorageStats();
    }
  });

  document.getElementById('batch-purge-btn')?.addEventListener('click', async () => {
    if (confirm(`Permanently delete ${state.selectedKeys.length} items?`)) {
      const res = await API.purgeTrash(state.selectedKeys);
      if (res.success) {
        UI.showToast(res.message, 'success');
        loadFiles();
        updateStorageStats();
      }
    }
  });

  // Logout
  document.getElementById('logout-btn')?.addEventListener('click', () => {
    API.setToken(null);
    showLoginModal();
  });
}

// Upload Execution with UI Progress
async function handleUpload(files) {
  if (!files || files.length === 0) return;
  const drawer = document.getElementById('upload-drawer');
  const uploadList = document.getElementById('upload-list');
  const drawerTitle = document.getElementById('upload-drawer-title');

  drawer.classList.add('show');
  drawerTitle.textContent = `Uploading ${files.length} file(s)...`;

  const itemDiv = document.createElement('div');
  itemDiv.className = 'upload-item';
  itemDiv.innerHTML = `
    <div class="upload-item-header">
      <span>Batch Upload (${files.length} items)</span>
      <span class="upload-percent">0%</span>
    </div>
    <div class="progress-bar-bg">
      <div class="progress-bar-fill"></div>
    </div>
  `;
  uploadList.prepend(itemDiv);

  const fill = itemDiv.querySelector('.progress-bar-fill');
  const percentText = itemDiv.querySelector('.upload-percent');

  try {
    await API.uploadFiles(state.currentPath, files, (percent) => {
      fill.style.width = `${percent}%`;
      percentText.textContent = `${percent}%`;
    });

    fill.style.backgroundColor = 'var(--accent-success)';
    percentText.textContent = 'Done';
    UI.showToast(`Successfully uploaded ${files.length} file(s)`, 'success');
    loadFiles();
    updateStorageStats();
  } catch (err) {
    fill.style.backgroundColor = 'var(--accent-danger)';
    percentText.textContent = 'Failed';
    UI.showToast(err.message || 'Upload failed', 'error');
  }
}

// Modal Handlers
function showLoginModal() {
  document.getElementById('login-modal').classList.add('show');
}
function hideLoginModal() {
  document.getElementById('login-modal').classList.remove('show');
}

// Login Form Submit
document.getElementById('login-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const password = document.getElementById('login-password').value;
  try {
    const res = await API.login(password);
    if (res.success && res.token) {
      API.setToken(res.token);
      hideLoginModal();
      initApp();
      UI.showToast('Welcome to your Personal Cloud!', 'success');
    } else {
      UI.showToast(res.message || 'Invalid password', 'error');
    }
  } catch (err) {
    UI.showToast('Login error: ' + err.message, 'error');
  }
});

// New Folder Submit
document.getElementById('create-folder-btn')?.addEventListener('click', async () => {
  const name = document.getElementById('new-folder-input').value.trim();
  if (!name) return;
  const res = await API.createFolder(state.currentPath, name);
  if (res.success) {
    document.getElementById('new-folder-modal').classList.remove('show');
    UI.showToast('Folder created', 'success');
    loadFiles();
  } else {
    UI.showToast(res.message, 'error');
  }
});

// Rename Modal
let itemToRename = null;
function openRenameModal(item) {
  itemToRename = item;
  document.getElementById('rename-input').value = item.name;
  document.getElementById('rename-modal').classList.add('show');
}

document.getElementById('save-rename-btn')?.addEventListener('click', async () => {
  if (!itemToRename) return;
  const newName = document.getElementById('rename-input').value.trim();
  if (!newName) return;
  const res = await API.renameItem(itemToRename.path, newName);
  if (res.success) {
    document.getElementById('rename-modal').classList.remove('show');
    UI.showToast('Renamed successfully', 'success');
    loadFiles();
  } else {
    UI.showToast(res.message, 'error');
  }
});

// Share Link Modal
let itemToShare = null;
function openShareModal(item) {
  itemToShare = item;
  document.getElementById('share-file-name').textContent = item.name;
  document.getElementById('share-result').style.display = 'none';
  document.getElementById('share-modal').classList.add('show');
}

document.getElementById('generate-share-btn')?.addEventListener('click', async () => {
  if (!itemToShare) return;
  const password = document.getElementById('share-password').value;
  const expireDays = document.getElementById('share-expiry').value;

  const res = await API.createShare(itemToShare.path, password, expireDays);
  if (res.success) {
    document.getElementById('share-result').style.display = 'block';
    document.getElementById('share-url-input').value = res.shareUrl;
  }
});

document.getElementById('copy-share-btn')?.addEventListener('click', () => {
  const input = document.getElementById('share-url-input');
  input.select();
  navigator.clipboard.writeText(input.value);
  UI.showToast('Link copied to clipboard!', 'success');
});
