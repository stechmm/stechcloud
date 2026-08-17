const fs = require('fs');
const path = require('path');

const DB_FILE = path.join(__dirname, 'data', 'metadata.json');

// Ensure data folder exists
const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

const defaultData = {
  starred: [], // Array of relative file paths
  shares: {}, // token -> { path, name, isFolder, passwordHash, expiresAt, createdAt, downloads }
  trash: [],  // Array of { id, originalPath, trashPath, name, size, isDirectory, deletedAt }
  settings: {
    theme: 'dark',
    allowPublicRegistration: false
  }
};

function loadDB() {
  try {
    if (fs.existsSync(DB_FILE)) {
      const raw = fs.readFileSync(DB_FILE, 'utf8');
      return { ...defaultData, ...JSON.parse(raw) };
    }
  } catch (err) {
    console.error('Error loading metadata DB:', err);
  }
  return { ...defaultData };
}

function saveDB(data) {
  try {
    fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf8');
  } catch (err) {
    console.error('Error saving metadata DB:', err);
  }
}

let db = loadDB();

module.exports = {
  get: () => db,
  save: () => saveDB(db),
  
  // Starred Helpers
  isStarred: (relPath) => db.starred.includes(relPath),
  toggleStar: (relPath) => {
    const idx = db.starred.indexOf(relPath);
    if (idx >= 0) {
      db.starred.splice(idx, 1);
      saveDB(db);
      return false;
    } else {
      db.starred.push(relPath);
      saveDB(db);
      return true;
    }
  },
  
  // Shares
  createShare: (token, shareData) => {
    db.shares[token] = shareData;
    saveDB(db);
  },
  getShare: (token) => db.shares[token],
  deleteShare: (token) => {
    delete db.shares[token];
    saveDB(db);
  },
  
  // Trash
  addToTrash: (trashRecord) => {
    db.trash.push(trashRecord);
    saveDB(db);
  },
  getTrash: () => db.trash,
  removeFromTrash: (trashId) => {
    const record = db.trash.find(t => t.id === trashId);
    db.trash = db.trash.filter(t => t.id !== trashId);
    saveDB(db);
    return record;
  },
  clearTrash: () => {
    const allTrash = [...db.trash];
    db.trash = [];
    saveDB(db);
    return allTrash;
  }
};
