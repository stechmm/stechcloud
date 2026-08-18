require('dotenv').config();
const express = require('express');
const cors = require('cors');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const mime = require('mime-types');
const archiver = require('archiver');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');
const db = require('./db');

const app = express();
const PORT = process.env.PORT || 8090;
const JWT_SECRET = process.env.JWT_SECRET || 'personal-cloud-super-secret-key-2026';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin123';
const STORAGE_ROOT = path.resolve(process.env.STORAGE_DIR || path.join(__dirname, 'storage'));
const TRASH_ROOT = path.resolve(path.join(__dirname, 'data', 'trash'));

// Ensure storage directories exist
if (!fs.existsSync(STORAGE_ROOT)) fs.mkdirSync(STORAGE_ROOT, { recursive: true });
if (!fs.existsSync(TRASH_ROOT)) fs.mkdirSync(TRASH_ROOT, { recursive: true });

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// Path validation helper (prevent directory traversal attacks)
function getSafePath(relativePath = '') {
  const normalized = path.normalize(relativePath).replace(/^(\.\.[\/\\])+/, '');
  const absolutePath = path.join(STORAGE_ROOT, normalized);
  if (!absolutePath.startsWith(STORAGE_ROOT)) {
    throw new Error('Access denied: path outside storage root');
  }
  return { absolutePath, relativePath: normalized.replace(/\\/g, '/') };
}

// Helper to determine file category
function getCategory(fileName, isDir) {
  if (isDir) return 'folder';
  const ext = path.extname(fileName).toLowerCase().replace('.', '');
  const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'heic', 'tiff'];
  const videoExts = ['mp4', 'mkv', 'webm', 'mov', 'avi', 'wmv', 'm4v', 'flv'];
  const audioExts = ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac', 'wma'];
  const docExts = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'md', 'rtf'];
  const archiveExts = ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'];
  const codeExts = ['js', 'ts', 'html', 'css', 'json', 'py', 'java', 'c', 'cpp', 'rs', 'go', 'php', 'sql', 'sh', 'yaml', 'yml'];

  if (imageExts.includes(ext)) return 'photo';
  if (videoExts.includes(ext)) return 'video';
  if (audioExts.includes(ext)) return 'audio';
  if (docExts.includes(ext)) return 'document';
  if (archiveExts.includes(ext)) return 'archive';
  if (codeExts.includes(ext)) return 'code';
  return 'other';
}

// Authentication Middleware
function authMiddleware(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ success: false, message: 'Authentication required' });
  }
  const token = authHeader.split(' ')[1];
  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ success: false, message: 'Invalid or expired session token' });
  }
}

// Query token auth middleware (for direct download links and video streaming tags)
function queryAuthMiddleware(req, res, next) {
  const token = req.query.token || (req.headers.authorization && req.headers.authorization.split(' ')[1]);
  if (!token) {
    return res.status(401).json({ success: false, message: 'Authentication required' });
  }
  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ success: false, message: 'Invalid or expired session token' });
  }
}

// --- AUTH API ---
app.post('/api/auth/login', (req, res) => {
  const { password } = req.body;
  if (!password) {
    return res.status(400).json({ success: false, message: 'Password is required' });
  }
  if (password === ADMIN_PASSWORD) {
    const token = jwt.sign({ user: 'admin', role: 'owner' }, JWT_SECRET, { expiresIn: '30d' });
    return res.json({ success: true, token, user: { username: 'Admin', role: 'owner' } });
  }
  return res.status(401).json({ success: false, message: 'Incorrect password' });
});

app.get('/api/auth/verify', authMiddleware, (req, res) => {
  res.json({ success: true, user: req.user });
});

// --- FILE EXPLORER API ---

// List files in a directory or filtered list (recent, starred, photos, videos, etc.)
app.get('/api/files', authMiddleware, async (req, res) => {
  try {
    const reqPath = req.query.path || '';
    const filter = req.query.filter || 'all'; // all, photos, videos, audio, docs, starred, recent, trash
    const searchQuery = (req.query.search || '').trim().toLowerCase();

    if (filter === 'trash') {
      const trashItems = db.getTrash().map(item => ({
        ...item,
        category: item.isDirectory ? 'folder' : getCategory(item.name, item.isDirectory)
      }));
      return res.json({ success: true, currentPath: '', items: trashItems, isTrash: true });
    }

    // Recursive search or category filter helper
    const getAllFilesRecursive = (dir, baseRel = '') => {
      let results = [];
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        const entryRel = path.posix.join(baseRel, entry.name);
        const entryAbs = path.join(dir, entry.name);
        const stats = fs.statSync(entryAbs);
        const isDir = entry.isDirectory();
        const category = getCategory(entry.name, isDir);

        if (isDir) {
          results.push({
            name: entry.name,
            path: entryRel,
            isDirectory: true,
            size: 0,
            modifiedAt: stats.mtime,
            category: 'folder',
            isStarred: db.isStarred(entryRel)
          });
          results = results.concat(getAllFilesRecursive(entryAbs, entryRel));
        } else {
          results.push({
            name: entry.name,
            path: entryRel,
            isDirectory: false,
            size: stats.size,
            modifiedAt: stats.mtime,
            category,
            mimeType: mime.lookup(entry.name) || 'application/octet-stream',
            isStarred: db.isStarred(entryRel)
          });
        }
      }
      return results;
    };

    if (searchQuery) {
      const all = getAllFilesRecursive(STORAGE_ROOT);
      const matched = all.filter(f => f.name.toLowerCase().includes(searchQuery));
      return res.json({ success: true, currentPath: '', items: matched, isFiltered: true });
    }

    if (filter === 'starred') {
      const all = getAllFilesRecursive(STORAGE_ROOT);
      const starred = all.filter(f => f.isStarred);
      return res.json({ success: true, currentPath: '', items: starred, isFiltered: true });
    }

    if (filter === 'recent') {
      const all = getAllFilesRecursive(STORAGE_ROOT).filter(f => !f.isDirectory);
      all.sort((a, b) => new Date(b.modifiedAt) - new Date(a.modifiedAt));
      return res.json({ success: true, currentPath: '', items: all.slice(0, 50), isFiltered: true });
    }

    if (['photos', 'videos', 'audio', 'docs'].includes(filter)) {
      const all = getAllFilesRecursive(STORAGE_ROOT).filter(f => !f.isDirectory);
      const catMap = { photos: 'photo', videos: 'video', audio: 'audio', docs: 'document' };
      const matched = all.filter(f => f.category === catMap[filter]);
      return res.json({ success: true, currentPath: '', items: matched, isFiltered: true });
    }

    // Normal folder browsing
    const { absolutePath, relativePath } = getSafePath(reqPath);
    if (!fs.existsSync(absolutePath)) {
      return res.status(404).json({ success: false, message: 'Folder not found' });
    }

    const stat = fs.statSync(absolutePath);
    if (!stat.isDirectory()) {
      return res.status(400).json({ success: false, message: 'Target is not a directory' });
    }

    const entries = fs.readdirSync(absolutePath, { withFileTypes: true });
    const items = entries.map(entry => {
      const itemAbs = path.join(absolutePath, entry.name);
      const itemRel = path.posix.join(relativePath, entry.name);
      const itemStat = fs.statSync(itemAbs);
      const isDir = entry.isDirectory();
      return {
        name: entry.name,
        path: itemRel,
        isDirectory: isDir,
        size: isDir ? 0 : itemStat.size,
        modifiedAt: itemStat.mtime,
        category: getCategory(entry.name, isDir),
        mimeType: isDir ? null : (mime.lookup(entry.name) || 'application/octet-stream'),
        isStarred: db.isStarred(itemRel)
      };
    });

    // Sort folders first, then alphabetically
    items.sort((a, b) => {
      if (a.isDirectory && !b.isDirectory) return -1;
      if (!a.isDirectory && b.isDirectory) return 1;
      return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
    });

    res.json({
      success: true,
      currentPath: relativePath,
      items
    });
  } catch (err) {
    console.error('Error listing files:', err);
    res.status(500).json({ success: false, message: err.message });
  }
});

// Configure Multer Storage for file uploads
const uploadStorage = multer.diskStorage({
  destination: (req, file, cb) => {
    try {
      const targetRel = req.body.path || '';
      // Support folder upload with relative webkit path if provided
      let subDir = '';
      if (req.body.relPath) {
        subDir = path.dirname(req.body.relPath);
      }
      const fullTargetRel = path.posix.join(targetRel, subDir);
      const { absolutePath } = getSafePath(fullTargetRel);
      
      if (!fs.existsSync(absolutePath)) {
        fs.mkdirSync(absolutePath, { recursive: true });
      }
      cb(null, absolutePath);
    } catch (err) {
      cb(err);
    }
  },
  filename: (req, file, cb) => {
    // Preserve original UTF-8 filename safely
    const originalName = Buffer.from(file.originalname, 'latin1').toString('utf8');
    cb(null, originalName);
  }
});

const upload = multer({
  storage: uploadStorage,
  limits: { fileSize: 10 * 1024 * 1024 * 1024 } // 10 GB limit per file
});

// Upload Files API
app.post('/api/upload', authMiddleware, upload.array('files'), (req, res) => {
  try {
    const uploaded = (req.files || []).map(f => ({
      name: f.filename,
      size: f.size
    }));
    res.json({ success: true, message: `Successfully uploaded ${uploaded.length} file(s)`, files: uploaded });
  } catch (err) {
    console.error('Upload error:', err);
    res.status(500).json({ success: false, message: err.message });
  }
});

// Create Folder API
app.post('/api/mkdir', authMiddleware, (req, res) => {
  try {
    const { path: parentPath, name } = req.body;
    if (!name || typeof name !== 'string' || name.trim() === '') {
      return res.status(400).json({ success: false, message: 'Valid folder name required' });
    }
    const cleanName = name.replace(/[<>:"/\\|?*]/g, '_').trim();
    const newFolderRel = path.posix.join(parentPath || '', cleanName);
    const { absolutePath } = getSafePath(newFolderRel);

    if (fs.existsSync(absolutePath)) {
      return res.status(400).json({ success: false, message: 'Folder or file already exists' });
    }

    fs.mkdirSync(absolutePath, { recursive: true });
    res.json({ success: true, message: 'Folder created successfully', path: newFolderRel });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// Rename File or Folder API
app.post('/api/rename', authMiddleware, (req, res) => {
  try {
    const { oldPath, newName } = req.body;
    if (!oldPath || !newName) {
      return res.status(400).json({ success: false, message: 'oldPath and newName required' });
    }
    const cleanName = newName.replace(/[<>:"/\\|?*]/g, '_').trim();
    const { absolutePath: oldAbs, relativePath: oldRel } = getSafePath(oldPath);
    
    if (!fs.existsSync(oldAbs)) {
      return res.status(404).json({ success: false, message: 'Source item not found' });
    }

    const parentRel = path.posix.dirname(oldRel);
    const newRel = parentRel === '.' ? cleanName : path.posix.join(parentRel, cleanName);
    const { absolutePath: newAbs } = getSafePath(newRel);

    if (fs.existsSync(newAbs)) {
      return res.status(400).json({ success: false, message: 'An item with this name already exists' });
    }

    fs.renameSync(oldAbs, newAbs);
    res.json({ success: true, message: 'Renamed successfully', newPath: newRel });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// Toggle Star API
app.post('/api/star', authMiddleware, (req, res) => {
  const { path: relPath } = req.body;
  if (!relPath) return res.status(400).json({ success: false, message: 'Path required' });
  const isStarred = db.toggleStar(relPath);
  res.json({ success: true, isStarred });
});

// Soft Delete (Move to Trash) API
app.post('/api/delete', authMiddleware, (req, res) => {
  try {
    const { paths } = req.body; // Array of relative paths
    if (!Array.isArray(paths) || paths.length === 0) {
      return res.status(400).json({ success: false, message: 'Paths array required' });
    }

    for (const relPath of paths) {
      const { absolutePath } = getSafePath(relPath);
      if (!fs.existsSync(absolutePath)) continue;

      const stat = fs.statSync(absolutePath);
      const isDir = stat.isDirectory();
      const trashId = crypto.randomUUID();
      const trashAbsPath = path.join(TRASH_ROOT, trashId);

      // Move to trash folder
      fs.renameSync(absolutePath, trashAbsPath);

      db.addToTrash({
        id: trashId,
        originalPath: relPath,
        trashPath: trashAbsPath,
        name: path.basename(relPath),
        size: isDir ? 0 : stat.size,
        isDirectory: isDir,
        deletedAt: new Date().toISOString()
      });
    }

    res.json({ success: true, message: `Moved ${paths.length} item(s) to trash` });
  } catch (err) {
    console.error('Delete error:', err);
    res.status(500).json({ success: false, message: err.message });
  }
});

// Restore from Trash API
app.post('/api/restore', authMiddleware, (req, res) => {
  try {
    const { ids } = req.body; // Array of trash record ids
    if (!Array.isArray(ids) || ids.length === 0) {
      return res.status(400).json({ success: false, message: 'Trash IDs required' });
    }

    for (const id of ids) {
      const record = db.removeFromTrash(id);
      if (!record || !fs.existsSync(record.trashPath)) continue;

      const { absolutePath: targetAbs } = getSafePath(record.originalPath);
      const targetDir = path.dirname(targetAbs);
      if (!fs.existsSync(targetDir)) {
        fs.mkdirSync(targetDir, { recursive: true });
      }

      fs.renameSync(record.trashPath, targetAbs);
    }

    res.json({ success: true, message: `Restored ${ids.length} item(s)` });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// Permanently Delete (Purge) API
app.post('/api/purge', authMiddleware, (req, res) => {
  try {
    const { ids } = req.body;
    if (!Array.isArray(ids) || ids.length === 0) {
      return res.status(400).json({ success: false, message: 'Trash IDs required' });
    }

    for (const id of ids) {
      const record = db.removeFromTrash(id);
      if (record && fs.existsSync(record.trashPath)) {
        fs.rmSync(record.trashPath, { recursive: true, force: true });
      }
    }

    res.json({ success: true, message: 'Permanently deleted' });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// Empty Trash API
app.post('/api/empty-trash', authMiddleware, (req, res) => {
  try {
    const allTrash = db.clearTrash();
    for (const item of allTrash) {
      if (fs.existsSync(item.trashPath)) {
        fs.rmSync(item.trashPath, { recursive: true, force: true });
      }
    }
    res.json({ success: true, message: 'Recycle bin emptied' });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// --- FILE PREVIEW & STREAMING API ---
app.get('/api/preview', queryAuthMiddleware, (req, res) => {
  try {
    const { path: relPath } = req.query;
    if (!relPath) return res.status(400).send('Path required');
    const { absolutePath } = getSafePath(relPath);

    if (!fs.existsSync(absolutePath)) {
      return res.status(404).send('File not found');
    }

    const stat = fs.statSync(absolutePath);
    if (stat.isDirectory()) {
      return res.status(400).send('Cannot preview directory');
    }

    const mimeType = mime.lookup(absolutePath) || 'application/octet-stream';
    const fileSize = stat.size;
    const range = req.headers.range;

    // Support HTTP Byte Range streaming for Videos & Audio seeking
    if (range) {
      const parts = range.replace(/bytes=/, '').split('-');
      const start = parseInt(parts[0], 10);
      const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
      const chunksize = (end - start) + 1;
      const file = fs.createReadStream(absolutePath, { start, end });

      const head = {
        'Content-Range': `bytes ${start}-${end}/${fileSize}`,
        'Accept-Ranges': 'bytes',
        'Content-Length': chunksize,
        'Content-Type': mimeType,
      };

      res.writeHead(206, head);
      file.pipe(res);
    } else {
      const head = {
        'Content-Length': fileSize,
        'Content-Type': mimeType,
        'Accept-Ranges': 'bytes'
      };
      res.writeHead(200, head);
      fs.createReadStream(absolutePath).pipe(res);
    }
  } catch (err) {
    console.error('Preview error:', err);
    res.status(500).send(err.message);
  }
});

// --- DOWNLOAD API (Single File & Batch ZIP) ---
app.get('/api/download', queryAuthMiddleware, (req, res) => {
  try {
    const { path: relPath, paths: multiPaths } = req.query;

    // Single File or Folder Download
    if (relPath) {
      const { absolutePath } = getSafePath(relPath);
      if (!fs.existsSync(absolutePath)) return res.status(404).send('File not found');
      const stat = fs.statSync(absolutePath);

      if (stat.isDirectory()) {
        const folderName = path.basename(relPath) || 'cloud_folder';
        res.setHeader('Content-Type', 'application/zip');
        res.setHeader('Content-Disposition', `attachment; filename="${encodeURIComponent(folderName)}.zip"`);
        const archive = archiver('zip', { zlib: { level: 6 } });
        archive.pipe(res);
        archive.directory(absolutePath, false);
        return archive.finalize();
      }

      const fileName = path.basename(absolutePath);
      res.download(absolutePath, fileName);
    } 
    // Multi-item Batch Zip Download
    else if (multiPaths) {
      const pathList = JSON.parse(multiPaths);
      res.setHeader('Content-Type', 'application/zip');
      res.setHeader('Content-Disposition', 'attachment; filename="cloud_files.zip"');
      const archive = archiver('zip', { zlib: { level: 6 } });
      archive.pipe(res);

      for (const p of pathList) {
        const { absolutePath } = getSafePath(p);
        if (fs.existsSync(absolutePath)) {
          const stat = fs.statSync(absolutePath);
          const base = path.basename(p);
          if (stat.isDirectory()) {
            archive.directory(absolutePath, base);
          } else {
            archive.file(absolutePath, { name: base });
          }
        }
      }
      archive.finalize();
    } else {
      res.status(400).send('Path or paths required');
    }
  } catch (err) {
    console.error('Download error:', err);
    res.status(500).send(err.message);
  }
});

// --- PUBLIC SHARE LINKS API ---
app.post('/api/share', authMiddleware, async (req, res) => {
  try {
    const { path: relPath, password, expireDays } = req.body;
    if (!relPath) return res.status(400).json({ success: false, message: 'Path is required' });

    const { absolutePath } = getSafePath(relPath);
    if (!fs.existsSync(absolutePath)) {
      return res.status(404).json({ success: false, message: 'Item not found' });
    }

    const stat = fs.statSync(absolutePath);
    const token = crypto.randomBytes(16).toString('hex');
    let passwordHash = null;
    if (password && password.trim()) {
      passwordHash = await bcrypt.hash(password.trim(), 10);
    }

    let expiresAt = null;
    if (expireDays && parseInt(expireDays, 10) > 0) {
      expiresAt = new Date(Date.now() + parseInt(expireDays, 10) * 24 * 60 * 60 * 1000).toISOString();
    }

    const shareData = {
      token,
      path: relPath,
      name: path.basename(relPath),
      isDirectory: stat.isDirectory(),
      size: stat.isDirectory() ? 0 : stat.size,
      hasPassword: !!passwordHash,
      passwordHash,
      expiresAt,
      createdAt: new Date().toISOString(),
      downloads: 0
    };

    db.createShare(token, shareData);

    const shareUrl = `${req.protocol}://${req.get('host')}/share.html?t=${token}`;
    res.json({ success: true, token, shareUrl, shareData });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// Get Public Shared Item Info
app.get('/api/public/share/:token', (req, res) => {
  const { token } = req.params;
  const share = db.getShare(token);
  if (!share) {
    return res.status(404).json({ success: false, message: 'Share link not found or expired' });
  }
  if (share.expiresAt && new Date(share.expiresAt) < new Date()) {
    return res.status(410).json({ success: false, message: 'Share link has expired' });
  }

  res.json({
    success: true,
    share: {
      name: share.name,
      size: share.size,
      isDirectory: share.isDirectory,
      hasPassword: share.hasPassword,
      expiresAt: share.expiresAt,
      createdAt: share.createdAt
    }
  });
});

// Download from Public Share Link
app.post('/api/public/share/:token/download', async (req, res) => {
  try {
    const { token } = req.params;
    const { password } = req.body;
    const share = db.getShare(token);

    if (!share) return res.status(404).send('Share link not found or expired');
    if (share.expiresAt && new Date(share.expiresAt) < new Date()) {
      return res.status(410).send('Share link has expired');
    }

    if (share.hasPassword) {
      if (!password) return res.status(401).send('Password required');
      const match = await bcrypt.compare(password, share.passwordHash);
      if (!match) return res.status(401).send('Invalid password');
    }

    const { absolutePath } = getSafePath(share.path);
    if (!fs.existsSync(absolutePath)) return res.status(404).send('File missing');

    share.downloads = (share.downloads || 0) + 1;
    db.save();

    const stat = fs.statSync(absolutePath);
    if (stat.isDirectory()) {
      res.setHeader('Content-Type', 'application/zip');
      res.setHeader('Content-Disposition', `attachment; filename="${encodeURIComponent(share.name)}.zip"`);
      const archive = archiver('zip', { zlib: { level: 6 } });
      archive.pipe(res);
      archive.directory(absolutePath, false);
      return archive.finalize();
    }

    res.download(absolutePath, share.name);
  } catch (err) {
    res.status(500).send(err.message);
  }
});

// --- STORAGE USAGE & STATS API ---
app.get('/api/stats', authMiddleware, (req, res) => {
  try {
    let totalFiles = 0;
    let totalFolders = 0;
    let totalSizeBytes = 0;
    const categorySizes = {
      photo: 0,
      video: 0,
      audio: 0,
      document: 0,
      archive: 0,
      code: 0,
      other: 0
    };

    function calculate(dir) {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          totalFolders++;
          calculate(full);
        } else {
          totalFiles++;
          const stat = fs.statSync(full);
          totalSizeBytes += stat.size;
          const cat = getCategory(entry.name, false);
          categorySizes[cat] = (categorySizes[cat] || 0) + stat.size;
        }
      }
    }

    calculate(STORAGE_ROOT);

    res.json({
      success: true,
      stats: {
        totalFiles,
        totalFolders,
        totalSizeBytes,
        categorySizes,
        trashCount: db.getTrash().length,
        sharesCount: Object.keys(db.get().shares || {}).length
      }
    });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// SPA Fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`=============================================`);
  console.log(`  🚀 Personal Cloud Storage Server Running!`);
  console.log(`  🌐 Local:   http://localhost:${PORT}`);
  console.log(`  📂 Storage: ${STORAGE_ROOT}`);
  console.log(`=============================================`);
});
