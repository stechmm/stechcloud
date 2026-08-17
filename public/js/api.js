// API Client for Personal Cloud
const API = {
  getToken() {
    return localStorage.getItem('cloud_jwt_token');
  },

  setToken(token) {
    if (token) localStorage.setItem('cloud_jwt_token', token);
    else localStorage.removeItem('cloud_jwt_token');
  },

  async request(endpoint, options = {}) {
    const headers = options.headers || {};
    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(endpoint, {
      ...options,
      headers
    });

    if (response.status === 401 && !endpoint.includes('/api/auth/login')) {
      this.setToken(null);
      window.dispatchEvent(new CustomEvent('auth-required'));
      throw new Error('Unauthorized');
    }

    return response;
  },

  async login(password) {
    const res = await this.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ password })
    });
    return res.json();
  },

  async verifyAuth() {
    if (!this.getToken()) return false;
    try {
      const res = await this.request('/api/auth/verify');
      const data = await res.json();
      return data.success;
    } catch {
      return false;
    }
  },

  async getFiles(path = '', filter = 'all', search = '') {
    const params = new URLSearchParams();
    if (path) params.append('path', path);
    if (filter && filter !== 'all') params.append('filter', filter);
    if (search) params.append('search', search);

    const res = await this.request(`/api/files?${params.toString()}`);
    return res.json();
  },

  async createFolder(parentPath, name) {
    const res = await this.request('/api/mkdir', {
      method: 'POST',
      body: JSON.stringify({ path: parentPath, name })
    });
    return res.json();
  },

  async renameItem(oldPath, newName) {
    const res = await this.request('/api/rename', {
      method: 'POST',
      body: JSON.stringify({ oldPath, newName })
    });
    return res.json();
  },

  async toggleStar(filePath) {
    const res = await this.request('/api/star', {
      method: 'POST',
      body: JSON.stringify({ path: filePath })
    });
    return res.json();
  },

  async deleteItems(paths) {
    const res = await this.request('/api/delete', {
      method: 'POST',
      body: JSON.stringify({ paths })
    });
    return res.json();
  },

  async restoreTrash(ids) {
    const res = await this.request('/api/restore', {
      method: 'POST',
      body: JSON.stringify({ ids })
    });
    return res.json();
  },

  async purgeTrash(ids) {
    const res = await this.request('/api/purge', {
      method: 'POST',
      body: JSON.stringify({ ids })
    });
    return res.json();
  },

  async emptyTrash() {
    const res = await this.request('/api/empty-trash', {
      method: 'POST'
    });
    return res.json();
  },

  async createShare(filePath, password = '', expireDays = 0) {
    const res = await this.request('/api/share', {
      method: 'POST',
      body: JSON.stringify({ path: filePath, password, expireDays })
    });
    return res.json();
  },

  async getStats() {
    const res = await this.request('/api/stats');
    return res.json();
  },

  // Upload with Progress Tracking
  uploadFiles(targetPath, fileList, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append('path', targetPath);

      for (let i = 0; i < fileList.length; i++) {
        const file = fileList[i];
        formData.append('files', file);
        // Include relative webkit path for folder upload
        if (file.webkitRelativePath) {
          formData.append('relPath', file.webkitRelativePath);
        }
      }

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && onProgress) {
          const percent = Math.round((e.loaded / e.total) * 100);
          onProgress(percent, e.loaded, e.total);
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText));
          } catch {
            resolve({ success: true });
          }
        } else {
          reject(new Error(xhr.responseText || 'Upload failed'));
        }
      });

      xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
      xhr.open('POST', '/api/upload');
      
      const token = this.getToken();
      if (token) {
        xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      }

      xhr.send(formData);
    });
  },

  getPreviewUrl(relPath) {
    const token = this.getToken();
    return `/api/preview?path=${encodeURIComponent(relPath)}&token=${encodeURIComponent(token)}`;
  },

  getDownloadUrl(relPath) {
    const token = this.getToken();
    return `/api/download?path=${encodeURIComponent(relPath)}&token=${encodeURIComponent(token)}`;
  },

  getBatchDownloadUrl(paths) {
    const token = this.getToken();
    return `/api/download?paths=${encodeURIComponent(JSON.stringify(paths))}&token=${encodeURIComponent(token)}`;
  }
};
