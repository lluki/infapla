// InFaPla - Frontend Application Controller
// Ensure fetch('/api/...') is routed relative to the app base path (e.g. /infapla/)
const _origFetch = window.fetch;
window.fetch = function(resource, init) {
  if (typeof resource === 'string' && resource.startsWith('/api/')) {
    const root = window.location.pathname.endsWith('/')
      ? window.location.pathname
      : window.location.pathname.replace(/\/[^\/]*$/, '/');
    resource = root + resource.slice(1);
  }
  return _origFetch.call(this, resource, init);
};

const App = {
  state: {
    currentView: 'overview',
    currentFilePath: null,
    currentFileType: null,
    currentFileContent: '',
    currentTab: 'wysiwyg',
    files: [],
    dataDir: null,
    gitDirty: false,
    expandedFolders: new Set(),
    currentDiffHash: null,
    currentDiffMessage: '',
    currentDiffRaw: '',
    diffFormat: 'side-by-side',
    ingredientSuggestions: null,
    currentShoppingData: null,
    aiStatus: 'idle',
  },

  init() {
    this.bindEvents();
    this.refreshAll();

    // Periodically poll filesystem and git status (every 3 seconds)
    setInterval(() => {
      this.loadFiles();
      this.checkGitStatus();
    }, 3000);

    // Refresh immediately when window or tab gains focus
    window.addEventListener('focus', () => {
      this.loadFiles();
      this.checkGitStatus();
      this.loadDashboardData();
      this.loadRecentChanges();
    });

    // Synchronize visual viewport (for mobile virtual keyboards)
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', () => {
        this.updateVisualViewport();
        this.scrollActiveChatToBottom();
      });
      window.visualViewport.addEventListener('scroll', () => {
        this.updateVisualViewport();
      });
    } else {
      window.addEventListener('resize', () => this.updateVisualViewport());
    }
    this.updateVisualViewport();
  },

  updateVisualViewport() {
    if (window.visualViewport) {
      const vh = window.visualViewport.height;
      const vt = window.visualViewport.offsetTop;
      document.documentElement.style.setProperty('--vvh', `${vh}px`);
      document.documentElement.style.setProperty('--vvt', `${vt}px`);
    } else {
      document.documentElement.style.setProperty('--vvh', `${window.innerHeight}px`);
      document.documentElement.style.setProperty('--vvt', '0px');
    }
  },

  scrollActiveChatToBottom() {
    const modal = document.getElementById('file-assistant-modal');
    if (modal && modal.style.display !== 'none') {
      const list = document.getElementById('file-chat-messages');
      if (list) list.scrollTop = list.scrollHeight;
    }
  },

  setModalOpen(isOpen) {
    if (isOpen) {
      if (!this._openModalsCount) {
        this._savedScrollY = window.scrollY || window.pageYOffset || 0;
        document.body.style.top = `-${this._savedScrollY}px`;
        document.body.classList.add('modal-open');
      }
      this._openModalsCount = (this._openModalsCount || 0) + 1;
      this.updateVisualViewport();
    } else {
      this._openModalsCount = Math.max(0, (this._openModalsCount || 1) - 1);
      if (this._openModalsCount === 0) {
        const savedY = this._savedScrollY || 0;
        document.body.classList.remove('modal-open');
        document.body.style.top = '';
        window.scrollTo(0, savedY);
      }
    }
  },

  bindEvents() {
    // ESC to close modals and drawer
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.closeDiffModal();
        this.closeBurgerMenu();
        this.closeFileAssistantModal();
        this.closeAddEventModal();
        this.closeIngredientPickerModal();
      }
    });

    const diffModal = document.getElementById('diff-modal');
    if (diffModal) {
      diffModal.addEventListener('click', (e) => {
        if (e.target === diffModal) {
          this.closeDiffModal();
        }
      });
    }

    // Ingredient picker input search and enter listener
    const pickerInput = document.getElementById('ingredient-picker-input');
    if (pickerInput) {
      pickerInput.addEventListener('input', (e) => {
        this.renderIngredientSuggestions(e.target.value);
      });
      pickerInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.submitIngredientPickerInput();
        }
      });
    }

    // Handle browser back/forward navigation
    window.addEventListener('popstate', (e) => {
      this.handleRouteFromUrl(false);
    });

    // Sync raw editor changes to state
    const rawEditor = document.getElementById('raw-editor-text');
    if (rawEditor) {
      rawEditor.addEventListener('input', (e) => {
        this.state.currentFileContent = e.target.value;
      });
    }

    // Ctrl+S / Cmd+S shortcut to save file
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        const editorView = document.getElementById('view-editor');
        if (editorView && editorView.style.display !== 'none') {
          e.preventDefault();
          this.saveCurrentFile();
        }
      }
    });
  },

  handleRouteFromUrl(push = false) {
    const params = new URLSearchParams(window.location.search);
    const filePath = params.get('file');
    const folderPath = params.get('folder');
    if (filePath) {
      this.openFile(filePath, push);
    } else if (folderPath) {
      this.openFolder(folderPath, push);
    } else {
      this.showOverview(push);
    }
  },


  showToast(message, type = 'info', actions = []) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    // Ensure only one notification is active: clear existing timeout and elements
    if (this._toastTimeout) {
      clearTimeout(this._toastTimeout);
      this._toastTimeout = null;
    }
    container.innerHTML = '';

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'toast-content';

    const iconSpan = document.createElement('span');
    iconSpan.className = 'toast-icon';
    iconSpan.textContent = type === 'success' ? '✓' : 'ℹ';
    contentDiv.appendChild(iconSpan);

    const msgSpan = document.createElement('span');
    msgSpan.className = 'toast-message';
    msgSpan.textContent = message;
    contentDiv.appendChild(msgSpan);

    toast.appendChild(contentDiv);

    if (actions && actions.length > 0) {
      const actionsDiv = document.createElement('div');
      actionsDiv.className = 'toast-actions';
      actions.forEach(act => {
        const btn = document.createElement('button');
        btn.className = `toast-btn ${act.primary ? 'primary' : ''}`;
        btn.textContent = act.label;
        btn.onclick = (e) => {
          e.stopPropagation();
          if (this._toastTimeout) {
            clearTimeout(this._toastTimeout);
            this._toastTimeout = null;
          }
          toast.remove();
          if (act.onClick) act.onClick();
        };
        actionsDiv.appendChild(btn);
      });
      toast.appendChild(actionsDiv);
    }

    const closeBtn = document.createElement('button');
    closeBtn.className = 'toast-close-btn';
    closeBtn.innerHTML = '✕';
    closeBtn.setAttribute('aria-label', 'Close notification');
    closeBtn.onclick = (e) => {
      e.stopPropagation();
      if (this._toastTimeout) {
        clearTimeout(this._toastTimeout);
        this._toastTimeout = null;
      }
      toast.remove();
    };
    toast.appendChild(closeBtn);

    container.appendChild(toast);

    // Give extra time if interactive actions are present
    const duration = (actions && actions.length > 0) ? 6500 : 3500;
    this._toastTimeout = setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => {
        if (toast.parentNode) toast.remove();
      }, 300);
    }, duration);
  },

  async refreshAll() {
    await Promise.all([
      this.loadFiles(),
      this.loadDashboardData(),
      this.loadRecentChanges(),
      this.checkGitStatus(),
      this.loadAppInfo()
    ]);
    this.handleRouteFromUrl(false);
  },

  async loadAppInfo() {
    try {
      const res = await fetch('/api/info');
      const data = await res.json();
      if (data.data_dir) {
        this.state.dataDir = data.data_dir;
      }
      const badge = document.getElementById('ai-model-badge');
      if (badge && data.model) {
        const shortModel = data.model.replace('gemini-', '').replace('-low', ' (Fast)');
        badge.textContent = `⚡ ${shortModel}`;
        badge.title = `Model: ${data.model} | Effort: ${data.effort}`;
      }
    } catch (e) {
      console.error('Info load error:', e);
    }
  },

  async loadFiles() {
    try {
      const res = await fetch(`/api/files?_t=${Date.now()}`, { cache: 'no-store' });
      const data = await res.json();
      this.state.files = data.files || [];
      this.renderFileTree();
      if (this.state.currentView === 'folder' && this.state.currentFolderPath) {
        this.renderFolderContents(this.state.currentFolderPath);
      }
    } catch (e) {
      console.error('Failed to load files:', e);
    }
  },

  toggleFolder(folderPath) {
    if (this.state.expandedFolders.has(folderPath)) {
      this.state.expandedFolders.delete(folderPath);
    } else {
      this.state.expandedFolders.add(folderPath);
    }
    this.renderFileTree();
  },

  buildFileTree(files) {
    const root = { name: '', path: '', isDir: true, subdirs: {}, files: [] };

    files.forEach(f => {
      const parts = f.path.split('/');
      let current = root;
      for (let i = 0; i < parts.length - 1; i++) {
        const seg = parts[i];
        const segPath = parts.slice(0, i + 1).join('/');
        if (!current.subdirs[seg]) {
          current.subdirs[seg] = {
            name: seg,
            path: segPath,
            isDir: true,
            subdirs: {},
            files: []
          };
        }
        current = current.subdirs[seg];
      }
      const fileName = parts[parts.length - 1];
      current.files.push({ ...f, displayName: fileName });
    });

    return root;
  },

  countFilesRecursive(node) {
    let count = node.files.length;
    for (const sub of Object.values(node.subdirs)) {
      count += this.countFilesRecursive(sub);
    }
    return count;
  },

  renderFileTree() {
    const list = document.getElementById('overview-folders-content');
    if (!list) return;
    list.innerHTML = '';

    const rootNode = this.buildFileTree(this.state.files);

    const iconMap = {
      shopping: '🛒',
      recipe: '🍲',
      mealplan: '📋',
      todo: '✅',
      calendar: '📅',
      markdown: '📝',
      generic: '📄'
    };

    const folderIconMap = {
      'shopping': '🛒',
      'shopping/recipes': '🍲',
      'shopping/mealplan': '📋',
      'todo': '✅',
      'calendar': '📅'
    };

    const renderNode = (node, container) => {
      // 1. Render Subfolders first
      const subFolderKeys = Object.keys(node.subdirs).sort();
      subFolderKeys.forEach(key => {
        const folder = node.subdirs[key];
        const isExpanded = this.state.expandedFolders.has(folder.path);
        const folderTotal = this.countFilesRecursive(folder);

        const folderEl = document.createElement('div');
        folderEl.className = 'folder-tree-item';
        const fIcon = folderIconMap[folder.path] || (isExpanded ? '📂' : '📁');

        folderEl.innerHTML = `
          <span class="folder-chevron">${isExpanded ? '▾' : '▸'}</span>
          <span>${fIcon}</span>
          <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600;">${folder.name}/</span>
          <button class="folder-open-detail-btn" title="Open this folder in detail view">Open Folder →</button>
          <span class="folder-count-badge">${folderTotal} ${folderTotal === 1 ? 'file' : 'files'}</span>
        `;
        folderEl.onclick = (e) => {
          e.stopPropagation();
          this.toggleFolder(folder.path);
        };
        const openBtn = folderEl.querySelector('.folder-open-detail-btn');
        if (openBtn) {
          openBtn.onclick = (e) => {
            e.stopPropagation();
            this.openFolder(folder.path);
          };
        }
        container.appendChild(folderEl);

        // If folder is expanded, render its children
        if (isExpanded) {
          const childrenDiv = document.createElement('div');
          childrenDiv.className = 'folder-children';
          renderNode(folder, childrenDiv);
          container.appendChild(childrenDiv);
        }
      });

      // 2. Render Direct Files in this folder
      const sortedFiles = [...node.files].sort((a, b) => a.displayName.localeCompare(b.displayName));
      sortedFiles.forEach(f => {
        const itemEl = document.createElement('div');
        itemEl.className = `file-tree-item ${this.state.currentFilePath === f.path ? 'active' : ''}`;
        const isSpecial = ['shopping', 'recipe', 'mealplan', 'todo', 'calendar'].includes(f.type);
        if (isSpecial) itemEl.classList.add('special-folder');

        const icon = iconMap[f.type] || '📄';
        itemEl.innerHTML = `
          <span>${icon}</span>
          <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${f.displayName}</span>
        `;
        itemEl.onclick = (e) => {
          e.stopPropagation();
          this.openFile(f.path);
        };
        container.appendChild(itemEl);
      });
    };

    const wrapper = document.createElement('div');
    wrapper.className = 'overview-folders-grid';
    renderNode(rootNode, wrapper);
    list.appendChild(wrapper);
  },

  async loadDashboardData() {
    // 1. Shopping preview
    try {
      const sRes = await fetch('/api/shopping');
      const sData = await sRes.json();
      const sCount = document.getElementById('dash-shopping-count');
      const sPrev = document.getElementById('dash-shopping-preview');
      if (sCount) sCount.textContent = `${sData.active_count || 0} pending`;
      if (sPrev) {
        const activeItems = (sData.items || []).filter(i => !i.done).slice(0, 4);
        if (activeItems.length === 0) {
          sPrev.innerHTML = '<em>All items checked off!</em>';
        } else {
          sPrev.innerHTML = activeItems.map(i => `<div>• ${i.text}</div>`).join('');
        }
      }
    } catch (e) {
      console.error('Shopping preview error:', e);
    }

    // 2. TODO preview
    try {
      const tRes = await fetch('/api/todo');
      const tData = await tRes.json();
      const tCount = document.getElementById('dash-todo-count');
      const tPrev = document.getElementById('dash-todo-preview');
      if (tCount) tCount.textContent = `${tData.active_count || 0} open`;
      if (tPrev) {
        const activeItems = (tData.items || []).filter(i => !i.done).slice(0, 4);
        if (activeItems.length === 0) {
          tPrev.innerHTML = '<em>No pending tasks!</em>';
        } else {
          tPrev.innerHTML = activeItems.map(i => `<div>• ${i.text}</div>`).join('');
        }
      }
    } catch (e) {
      console.error('Todo preview error:', e);
    }

    // 3. Calendar preview
    try {
      const cRes = await fetch('/api/calendar');
      const cData = await cRes.json();
      if (cData.ics_url) this.state.calendarIcsUrl = cData.ics_url;
      const cCount = document.getElementById('dash-cal-count');
      const cPrev = document.getElementById('dash-cal-preview');
      const events = cData.events || [];
      if (cCount) cCount.textContent = `${events.length} upcoming`;
      if (cPrev) {
        if (events.length === 0) {
          cPrev.innerHTML = '<em>No upcoming events scheduled.</em>';
        } else {
          cPrev.innerHTML = events.slice(0, 3).map(ev => `
            <div><strong>${ev.summary}</strong> <small style="color:var(--text-muted)">(${ev.start_str || 'TBD'})</small></div>
          `).join('');
        }
      }
    } catch (e) {
      console.error('Calendar preview error:', e);
    }

    // 4. Recipe preview
    const rPrev = document.getElementById('dash-recipe-preview');
    if (rPrev) {
      const recipes = this.state.files.filter(f => f.type === 'recipe');
      if (recipes.length === 0) {
        rPrev.innerHTML = '<em>No recipes saved yet.</em>';
      } else {
        rPrev.innerHTML = recipes.slice(0, 3).map(r => `<div>🍲 ${r.name.replace('.md', '')}</div>`).join('');
      }
    }
  },

  async loadRecentChanges() {
    const container = document.getElementById('recent-changes-content');
    if (!container) return;
    try {
      const [historyRes, statusRes] = await Promise.all([
        fetch('/api/git/history?limit=5'),
        fetch('/api/git/status')
      ]);
      const historyData = await historyRes.json();
      const statusData = await statusRes.json();
      const commits = historyData.commits || [];
      const dirty = statusData.dirty;
      const changedFiles = statusData.changed_files || [];

      container.innerHTML = '';

      // Top Entry: Uncommitted Changes banner with Sync button
      const uncommittedEl = document.createElement('div');
      uncommittedEl.className = `uncommitted-banner ${dirty ? '' : 'clean'}`;

      let uncommittedListHtml = '';
      if (dirty && changedFiles.length > 0) {
        uncommittedListHtml = `
          <div class="commit-files">
            ${changedFiles.map(f => `
              <div class="file-diff-row">
                <button class="file-link-title" onclick="App.openFile('${f.path}')" title="Open ${f.path}">
                  <span>📄</span>
                  <span>${f.path}</span>
                  <small style="color: var(--text-muted); font-size: 0.7rem; font-family: sans-serif;">(${f.status || 'modified'})</small>
                </button>
                <button class="diff-action-btn" onclick="App.showFileDiff(null, '${f.path}', 'Uncommitted changes in ${f.path}')">
                  Diff
                </button>
              </div>
            `).join('')}
          </div>
        `;
      }

      uncommittedEl.innerHTML = `
        <div class="uncommitted-header">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-size: 1.1rem;">${dirty ? '⚡' : '✓'}</span>
            <div>
              <div style="font-weight: 700; font-size: 0.9rem; color: var(--text-primary);">
                ${dirty ? `Uncommitted changes (${changedFiles.length} files modified)` : 'Uncommitted changes: Clean working tree'}
              </div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">
                ${dirty ? 'Local changes not yet committed to Git' : 'All working tree changes are committed'}
              </div>
            </div>
          </div>
          <button class="sync-btn" id="git-sync-btn" onclick="App.syncGit()" title="Commit, pull, merge & push">
            <span>🔄</span> <span>Sync</span>
          </button>
        </div>
        ${uncommittedListHtml}
      `;
      container.appendChild(uncommittedEl);

      // Section: Recent Commits
      if (commits.length === 0) {
        const emptyDiv = document.createElement('div');
        emptyDiv.style.color = 'var(--text-muted)';
        emptyDiv.style.fontSize = '0.85rem';
        emptyDiv.style.padding = '0.5rem 0';
        emptyDiv.innerHTML = '<em>No commit history yet.</em>';
        container.appendChild(emptyDiv);
        return;
      }

      commits.forEach(c => {
        const row = document.createElement('div');
        row.className = 'commit-row';

        // Vertical list of changed files with diff button per file
        let filesHtml = '';
        if (c.files && c.files.length > 0) {
          filesHtml = `
            <div class="commit-files">
              ${c.files.map(f => `
                <div class="file-diff-row">
                  <button class="file-link-title" onclick="App.openFile('${f}')" title="Open ${f}">
                    <span>📄</span>
                    <span>${f}</span>
                  </button>
                  <button class="diff-action-btn" onclick="App.showFileDiff('${c.hash}', '${f}', '${encodeURIComponent(c.message || '')}')">
                    Diff
                  </button>
                </div>
              `).join('')}
            </div>
          `;
        } else {
          filesHtml = '<div style="font-size: 0.75rem; color: var(--text-muted); font-style: italic; margin-top: 0.25rem;">No files changed or initial commit</div>';
        }

        row.innerHTML = `
          <div class="commit-top">
            <div class="commit-message">
              <span>📌</span>
              <span>${c.message || 'No commit message'}</span>
            </div>
            <div class="commit-meta">
              <span class="commit-hash-pill" title="Commit Hash">${c.short_hash}</span>
              <span>by ${c.author || 'Family'}</span>
              <span>• ${c.date}</span>
            </div>
          </div>
          ${filesHtml}
        `;
        container.appendChild(row);
      });
    } catch (e) {
      console.error('Recent changes load error:', e);
      container.innerHTML = '<div style="color: var(--danger); font-size: 0.85rem;">Failed to load recent changes.</div>';
    }
  },

  async syncGit() {
    const syncBtn = document.getElementById('git-sync-btn');
    if (syncBtn) {
      syncBtn.disabled = true;
      syncBtn.innerHTML = '<span>⏳</span> <span>Syncing...</span>';
    }

    try {
      const res = await fetch('/api/git/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: `Sync: ${new Date().toLocaleString()}` })
      });
      const data = await res.json();
      if (data.success) {
        this.showToast(data.message || 'Synced successfully', 'success');
        await this.loadRecentChanges();
      } else {
        this.showToast('Sync error: ' + (data.error || 'unknown'), 'info');
      }
    } catch (e) {
      this.showToast('Sync failed: ' + e.message, 'info');
    } finally {
      if (syncBtn) {
        syncBtn.disabled = false;
        syncBtn.innerHTML = '<span>🔄</span> <span>Sync</span>';
      }
    }
  },

  async showFileDiff(commitHash, filePath, encodedMsgOrTitle) {
    const modal = document.getElementById('diff-modal');
    const content = document.getElementById('diff-modal-content');
    const title = document.getElementById('diff-modal-title');
    const subtitle = document.getElementById('diff-modal-subtitle');
    if (!modal || !content) return;

    this.state.currentDiffHash = commitHash;
    const msg = decodeURIComponent(encodedMsgOrTitle || '');
    this.state.currentDiffMessage = msg;

    if (title) {
      title.textContent = filePath ? `Diff: ${filePath}` : (msg || 'Diff');
    }
    if (subtitle) {
      subtitle.textContent = commitHash
        ? `Commit ${commitHash.substring(0, 7)}: ${msg}`
        : 'Uncommitted working tree changes vs HEAD';
    }

    content.innerHTML = '<div style="padding: 2.5rem; text-align: center; color: var(--text-muted);">Fetching file diff...</div>';
    modal.style.display = 'flex';
    this.setModalOpen(true);

    try {
      let url = '/api/git/diff?';
      const params = new URLSearchParams();
      if (commitHash) params.set('commit', commitHash);
      if (filePath) params.set('file', filePath);
      url += params.toString();

      const res = await fetch(url);
      const data = await res.json();
      this.state.currentDiffRaw = data.diff || '';
      this.renderDiff();
    } catch (e) {
      console.error('Failed to load file diff:', e);
      content.innerHTML = `<div style="padding: 2rem; color: var(--danger);">Failed to load diff: ${e.message}</div>`;
    }
  },

  renderDiff() {
    const content = document.getElementById('diff-modal-content');
    if (!content) return;

    const diffText = this.state.currentDiffRaw;
    if (!diffText || !diffText.trim()) {
      content.innerHTML = '<div style="padding: 2.5rem; text-align: center; color: var(--text-muted);"><em>No textual diff in this commit (e.g. empty commit or binary file changes).</em></div>';
      return;
    }

    try {
      if (typeof Diff2Html !== 'undefined' && Diff2Html.html) {
        const diffHtml = Diff2Html.html(diffText, {
          drawFileList: true,
          matching: 'lines',
          outputFormat: this.state.diffFormat,
          renderNothingWhenEmpty: false,
          colorScheme: 'dark'
        });
        content.innerHTML = `<div class="d2h-dark-color-scheme">${diffHtml}</div>`;
      } else {
        // Fallback to preformatted diff
        content.innerHTML = `<pre style="color: #eee; font-family: var(--font-mono); font-size: 0.85rem; white-space: pre-wrap;">${this.escapeHtml(diffText)}</pre>`;
      }
    } catch (err) {
      console.error('Diff render error:', err);
      content.innerHTML = `<pre style="color: #eee; font-family: var(--font-mono); font-size: 0.85rem; white-space: pre-wrap;">${this.escapeHtml(diffText)}</pre>`;
    }
  },

  toggleDiffFormat(format) {
    this.state.diffFormat = format;
    const btnSide = document.getElementById('diff-toggle-side');
    const btnLine = document.getElementById('diff-toggle-line');
    if (btnSide && btnLine) {
      btnSide.classList.toggle('active', format === 'side-by-side');
      btnLine.classList.toggle('active', format === 'line-by-line');
    }
    this.renderDiff();
  },

  closeDiffModal() {
    const modal = document.getElementById('diff-modal');
    if (modal && modal.style.display !== 'none') {
      modal.style.display = 'none';
      this.setModalOpen(false);
    }
    this.state.currentDiffHash = null;
    this.state.currentDiffRaw = '';
  },

  escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  },

  async checkGitStatus() {
    try {
      const res = await fetch('/api/git/status');
      const data = await res.json();
      const prevDirty = this.state.gitDirty;
      this.state.gitDirty = data.dirty;
      // If dirty status changed, refresh the Recent changes uncommitted section
      if (prevDirty !== data.dirty && this.state.currentView === 'overview') {
        this.loadRecentChanges();
      }
    } catch (e) {
      console.error('Git status error:', e);
    }
  },

  async manualCommit() {
    try {
      const res = await fetch('/api/git/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: `Manual commit: ${new Date().toLocaleString()}` })
      });
      const data = await res.json();
      if (data.success) {
        this.showToast('Changes committed to Git', 'success');
        this.checkGitStatus();
        this.loadGitHistory();
      }
    } catch (e) {
      this.showToast('Commit failed', 'info');
    }
  },

  showOverview(push = true) {
    this.state.currentView = 'overview';
    this.state.currentFilePath = null;
    this.state.currentFolderPath = null;
    this.state.currentFileType = null;
    document.getElementById('view-overview').style.display = 'flex';
    document.getElementById('view-editor').style.display = 'none';
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    const navOv = document.getElementById('nav-overview');
    if (navOv) navOv.classList.add('active');

    if (push) {
      const newUrl = window.location.pathname;
      if (window.location.search) {
        history.pushState({ view: 'overview' }, '', newUrl);
      }
    }

    this.updateBurgerMenuState();
    this.renderFileTree();
    this.loadDashboardData();
  },

  openCalendarView() {
    const calFile = this.state.files.find(f => f.type === 'calendar');
    this.openFile(calFile ? calFile.path : 'calendar/family.ics');
  },

  async openFile(path, push = true) {
    this.state.currentView = 'editor';
    this.state.currentFilePath = path;
    document.getElementById('view-overview').style.display = 'none';
    document.getElementById('view-editor').style.display = 'flex';

    if (push) {
      const newUrl = `${window.location.pathname}?file=${encodeURIComponent(path)}`;
      if (window.location.search !== `?file=${encodeURIComponent(path)}`) {
        history.pushState({ view: 'editor', path }, '', newUrl);
      }
    }

    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    // Highlight specific nav buttons if match
    if (path === 'shopping/list.md') {
      const btn = document.querySelector(".header-nav button[onclick*='shopping/list.md']");
      if (btn) btn.classList.add('active');
    } else if (path === 'todo/list.md') {
      const btn = document.querySelector(".header-nav button[onclick*='todo/list.md']");
      if (btn) btn.classList.add('active');
    } else if (path.endsWith('.ics')) {
      const btn = document.querySelector(".header-nav button[onclick*='calendar']");
      if (btn) btn.classList.add('active');
    }

    this.renderPathBreadcrumbs(path, false);
    const ctxBadge = document.getElementById('file-chat-context-badge');
    if (ctxBadge) ctxBadge.textContent = `Context: ${path}`;

    // Automatically expand parent folders so opened file is visible in tree
    const pathParts = path.split('/');
    for (let i = 1; i < pathParts.length; i++) {
      this.state.expandedFolders.add(pathParts.slice(0, i).join('/'));
    }

    this.renderFileTree();

    try {
      const res = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
      const data = await res.json();
      this.state.currentFileType = data.type;
      this.state.currentFileContent = data.content;

      // Update RAW editor textarea
      const rawTextarea = document.getElementById('raw-editor-text');
      if (rawTextarea) rawTextarea.value = data.content;

      // Update WYSIWYG
      this.renderWYSIWYG(data.content);

      // Handle Special and Mode Tabs
      const isSpecial = ['shopping', 'recipe', 'mealplan', 'todo', 'calendar'].includes(data.type);
      const shoppingActions = document.getElementById('shopping-special-actions');

      if (shoppingActions) {
        shoppingActions.style.display = (data.type === 'shopping') ? 'flex' : 'none';
      }

      // If available open interactive, otherwise choose visual
      if (isSpecial) {
        this.switchEditorTab('special');
        this.renderSpecialView(data.type, path, data.content);
      } else {
        this.switchEditorTab('wysiwyg');
      }

      this.updateBurgerMenuState();

    } catch (e) {
      this.showToast('Failed to open file: ' + e.message, 'info');
    }
  },

  switchEditorTab(tabName) {
    // Sync current raw editor content to state if switching away from raw
    const rawTextarea = document.getElementById('raw-editor-text');
    if (this.state.currentTab === 'raw' && rawTextarea) {
      this.state.currentFileContent = rawTextarea.value;
    }

    this.state.currentTab = tabName;

    const paneSpecial = document.getElementById('pane-special');
    const paneWysiwyg = document.getElementById('pane-wysiwyg');
    const paneRaw = document.getElementById('pane-raw');

    [paneSpecial, paneWysiwyg, paneRaw].forEach(p => { if (p) p.style.display = 'none'; });

    if (tabName === 'special') {
      if (paneSpecial) paneSpecial.style.display = 'block';
      // Re-render special view with current content so changes in raw immediately reflect in interactive mode
      if (this.state.currentFileType && this.state.currentFilePath) {
        this.renderSpecialView(this.state.currentFileType, this.state.currentFilePath, this.state.currentFileContent);
      }
    } else if (tabName === 'raw') {
      if (paneRaw) paneRaw.style.display = 'flex';
      if (rawTextarea) rawTextarea.value = this.state.currentFileContent;
    } else {
      if (paneWysiwyg) paneWysiwyg.style.display = 'flex';
      this.renderWYSIWYG(this.state.currentFileContent);
    }

    // Update current mode badge in editor toolbar
    const badge = document.getElementById('editor-mode-badge');
    if (badge) {
      if (tabName === 'special') badge.textContent = 'Interactive';
      else if (tabName === 'raw') badge.textContent = 'Raw';
      else badge.textContent = 'Visual';
    }

    this.updateBurgerMenuState();
  },

  renderWYSIWYG(markdownText) {
    const content = document.getElementById('wysiwyg-content');
    if (!content) return;
    content.innerHTML = this.parseMarkdownToHTML(markdownText);
  },

  parseMarkdownToHTML(md) {
    if (!md) return '<em>(Empty file)</em>';
    let html = md
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Headings
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // Bold & italic
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/gim, '<em>$1</em>');
    html = html.replace(/~~(.*?)~~/gim, '<del>$1</del>');

    // Checkboxes
    html = html.replace(/^- \[x\] (.*$)/gim, '<div style="margin: 0.2rem 0; opacity: 0.6; text-decoration: line-through;"><input type="checkbox" checked disabled> $1</div>');
    html = html.replace(/^- \[ \] (.*$)/gim, '<div style="margin: 0.2rem 0;"><input type="checkbox" disabled> $1</div>');

    // Bullets
    html = html.replace(/^- (.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/gims, '<ul>$1</ul>');

    // Numbered lists
    html = html.replace(/^\d+\.\s+(.*$)/gim, '<div style="margin: 0.25rem 0; padding-left: 0.25rem;"><span style="color: var(--accent); font-weight: 600;">$&</span></div>');

    // Links: [label](url) -> resolve file URLs into clean relative paths
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/gim, (match, label, href) => {
      const cleanHref = href.trim();
      if (cleanHref.startsWith('http://') || cleanHref.startsWith('https://')) {
        return `<a href="${cleanHref}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      }
      const relPath = this.normalizeFilePath(cleanHref, this.state.currentFilePath);
      return `<a href="javascript:App.handleLinkClick('${relPath}')">${label}</a>`;
    });

    // Inline code: `code`
    html = html.replace(/`([^`]+)`/gim, '<code>$1</code>');

    // Paragraph breaks
    html = html.replace(/\n\n/gim, '<p></p>');

    return html;
  },

  normalizeFilePath(rawPath, baseContextPath = null) {
    if (!rawPath) return '';
    let p = String(rawPath).trim();

    // Strip line fragments like #L1-L10 or #section
    p = p.split('#')[0];

    // Strip query parameters
    p = p.split('?')[0];

    // Strip file:// scheme (case-insensitive)
    p = p.replace(/^file:\/{2,3}/i, '');

    // Decode URI components
    try {
      p = decodeURIComponent(p);
    } catch (e) {}

    // Match active dataDir from server if available
    if (this.state.dataDir && p.startsWith(this.state.dataDir)) {
      p = p.substring(this.state.dataDir.length);
    }

    // Match /data/ directory boundary
    const dataIdx = p.indexOf('/data/');
    if (dataIdx !== -1) {
      p = p.substring(dataIdx + 6);
    } else if (p.startsWith('data/')) {
      p = p.substring(5);
    } else if (p.startsWith('/data/')) {
      p = p.substring(6);
    } else {
      const repoIdx = p.indexOf('/InFaPla/');
      if (repoIdx !== -1) {
        p = p.substring(repoIdx + 9);
      }
    }

    const resolveSegments = (str) => {
      const parts = str.split('/');
      const stack = [];
      for (const seg of parts) {
        if (!seg || seg === '.') continue;
        if (seg === '..') {
          if (stack.length > 0) stack.pop();
        } else {
          stack.push(seg);
        }
      }
      return stack.join('/');
    };

    // Determine base directory from baseContextPath or current state
    let baseDir = '';
    const base = baseContextPath !== null ? baseContextPath : (this.state.currentFilePath || this.state.currentFolderPath || '');
    if (base) {
      if (baseContextPath === null && this.state.currentFolderPath && !this.state.currentFilePath) {
        baseDir = base.replace(/^\/+/, '').replace(/\/+$/, '');
      } else {
        const parts = base.replace(/^\/+/, '').split('/');
        parts.pop(); // remove file name
        baseDir = parts.join('/');
      }
    }

    // If p begins with / (root relative in repo/data)
    if (p.startsWith('/')) {
      return resolveSegments(p.replace(/^\/+/, ''));
    }

    // If explicitly relative with ./ or ../
    if (p.startsWith('./') || p.startsWith('../')) {
      const combined = baseDir ? `${baseDir}/${p}` : p;
      return resolveSegments(combined);
    }

    // If p matches an existing file path exactly, it is already a clean repo path
    if (this.state.files && this.state.files.some(f => f.path === p)) {
      return p;
    }

    // If resolving against baseDir matches an existing file path
    if (baseDir) {
      const candidate = resolveSegments(`${baseDir}/${p}`);
      if (this.state.files && this.state.files.some(f => f.path === candidate)) {
        return candidate;
      }
    }

    // If p contains segments with .. or .
    if (p.includes('/.') || p.includes('./') || p.includes('..')) {
      const combined = baseDir ? `${baseDir}/${p}` : p;
      return resolveSegments(combined);
    }

    // If baseDir exists and p doesn't have slashes, resolve relative to baseDir
    if (baseDir && !p.includes('/')) {
      return resolveSegments(`${baseDir}/${p}`);
    }

    return resolveSegments(p);
  },

  handleLinkClick(href) {
    if (!href) return;
    if (href.startsWith('http://') || href.startsWith('https://')) {
      window.open(href, '_blank');
      return;
    }
    const cleanPath = this.normalizeFilePath(href);
    if (!cleanPath) return;

    // Check if cleanPath represents a folder
    const isFolder = cleanPath.endsWith('/') ||
      (this.state.files && this.state.files.some(f => f.path.startsWith(cleanPath + '/')) && !this.state.files.some(f => f.path === cleanPath)) ||
      (!cleanPath.includes('.') && (!this.state.files || !this.state.files.some(f => f.path === cleanPath)));

    if (isFolder) {
      this.openFolder(cleanPath.replace(/\/+$/, ''));
    } else {
      this.openFile(cleanPath);
    }
  },

  async renderSpecialView(type, path, content) {
    // Hide all special subcontainers
    ['shopping', 'recipe', 'mealplan', 'todo', 'calendar', 'folder'].forEach(k => {
      const c = document.getElementById(`special-${k}-container`);
      if (c) c.style.display = 'none';
    });

    if (type === 'shopping') {
      const container = document.getElementById('special-shopping-container');
      container.style.display = 'flex';
      await this.loadSpecialShoppingUI();
    } else if (type === 'recipe') {
      const container = document.getElementById('special-recipe-container');
      container.style.display = 'flex';
      await this.loadSpecialRecipeUI(path);
    } else if (type === 'mealplan') {
      const container = document.getElementById('special-mealplan-container');
      container.style.display = 'block';
      await this.loadSpecialMealplanUI(path);
    } else if (type === 'todo') {
      const container = document.getElementById('special-todo-container');
      container.style.display = 'flex';
      await this.loadSpecialTodoUI();
    } else if (type === 'calendar') {
      const container = document.getElementById('special-calendar-container');
      container.style.display = 'flex';
      await this.loadSpecialCalendarUI();
    } else if (type === 'folder') {
      const container = document.getElementById('special-folder-container');
      container.style.display = 'flex';
      this.renderFolderContents(path);
    }
  },

  // ===== Special Shopping UI =====
  async loadSpecialShoppingUI() {
    const listDiv = document.getElementById('special-shopping-items');
    if (!listDiv) return;
    try {
      const res = await fetch('/api/shopping');
      const data = await res.json();
      this.state.currentShoppingData = data;
      // Pre-fetch suggestions once in background for zero-latency autocomplete
      this.prefetchShoppingSuggestions();

      listDiv.innerHTML = '';

      const activeItems = (data.items || []).filter(i => !i.done);
      const doneItems = (data.items || []).filter(i => i.done);

      if (activeItems.length === 0 && doneItems.length === 0) {
        listDiv.innerHTML = '<em>Shopping list is empty!</em>';
        return;
      }

      // Render Active items grouped by category
      const byCat = {};
      activeItems.forEach(item => {
        const cat = item.category || 'General';
        if (!byCat[cat]) byCat[cat] = [];
        byCat[cat].push(item);
      });

      Object.keys(byCat).forEach(cat => {
        if (cat !== 'General') {
          const catHeader = document.createElement('div');
          catHeader.className = 'category-header';
          catHeader.textContent = cat;
          listDiv.appendChild(catHeader);
        }
        byCat[cat].forEach(item => {
          listDiv.appendChild(this.createShoppingItemRow(item));
        });
      });

      // Render Done items at the bottom with strike-through
      if (doneItems.length > 0) {
        const completedHeader = document.createElement('div');
        completedHeader.className = 'category-header';
        completedHeader.textContent = 'Completed';
        listDiv.appendChild(completedHeader);

        doneItems.forEach(item => {
          listDiv.appendChild(this.createShoppingItemRow(item));
        });
      }

    } catch (e) {
      console.error('Error loading shopping UI:', e);
    }
  },

  createShoppingItemRow(item) {
    const row = document.createElement('div');
    row.className = `item-row ${item.done ? 'done' : ''}`;
    row.innerHTML = `
      <input type="checkbox" class="item-checkbox" ${item.done ? 'checked' : ''}>
      <span class="item-text">${item.text}</span>
    `;

    const chk = row.querySelector('.item-checkbox');
    chk.addEventListener('change', async (e) => {
      e.stopPropagation();
      await this.toggleShoppingItem(item.id || item.text);
    });

    row.addEventListener('click', async (e) => {
      if (e.target !== chk) {
        await this.toggleShoppingItem(item.id || item.text);
      }
    });

    return row;
  },

  async toggleShoppingItem(itemId) {
    try {
      const res = await fetch('/api/shopping/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: itemId })
      });
      await res.json();
      await this.loadSpecialShoppingUI();
      // Reload file content in editor background
      this.syncCurrentFileContent();
    } catch (e) {
      this.showToast('Toggle failed', 'info');
    }
  },

  async addShoppingItem() {
    const input = document.getElementById('add-shopping-input');
    const text = input ? input.value.trim() : '';
    if (!text) {
      this.openIngredientPickerModal();
      return;
    }

    try {
      await fetch('/api/shopping/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      input.value = '';
      await this.loadSpecialShoppingUI();
      this.syncCurrentFileContent();
      this.showToast(`Added "${text}" to shopping list`, 'success');
    } catch (e) {
      this.showToast('Failed to add item', 'info');
    }
  },

  async removeShoppingItem(itemId) {
    try {
      await fetch('/api/shopping/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: itemId })
      });
      await this.loadSpecialShoppingUI();
      this.syncCurrentFileContent();
    } catch (e) {
      this.showToast('Failed to remove item', 'info');
    }
  },

  async archiveShoppingList() {
    try {
      const res = await fetch('/api/shopping/archive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      this.state.ingredientSuggestions = null;
      await this.loadSpecialShoppingUI();
      this.syncCurrentFileContent();
      this.showToast(`Archived shopping list to ${data.archived_to || 'archive'}!`, 'success');
      this.loadDashboardData();
      this.loadFiles();
    } catch (e) {
      this.showToast('Failed to archive shopping list', 'info');
    }
  },

  async clearShoppingChecked() {
    return this.archiveShoppingList();
  },

  // ===== Ingredient Picker Modal & Suggestions =====
  cleanItemName(text) {
    if (!text) return '';
    let s = text.trim();
    if (s.includes(' category: ')) {
      s = s.substring(0, s.lastIndexOf(' category: ')).trim();
    }
    s = s.replace(/^[-*+]\s+(\[[ xX]\]\s*)?/, '');
    s = s.replace(/^~~(.*)~~$/, '$1').trim();
    s = s.replace(/^(?:(?:ca\.?|approx\.?|about|to)\s+)?(?:(?:\d+(?:[./\-\u2013\u2014]\d+)?(?:\s+to\s+\d+(?:[./\-\u2013\u2014]\d+)?)?|\b(?:a|an|one|two|three|ein|eine|einer|eines|etwas|some)\b)\s*(?:[xX*]\s*)?(?:g|kg|oz|lb|lbs|ml|l|cl|dl|tsp|tbsp|el|tl|cup|cups|pinch|pinches|prise|prisen|glas|gläser|stk|stk\.|stück|stücke|bunch|bunches|bund|clove|cloves|zehe|zehen|can|cans|dose|dosen|slice|slices|scheibe|scheiben|piece|pieces|bottle|bottles|flasche|flaschen|packung|packungen|becher|drop|drops|tropfen|inch|small|medium|large|große?|mittlere?|kleine?)\b\s*|\d+(?:[./\-\u2013\u2014]\d+)?\s*(?:[xX*]\s*)?)(?:of\s+|von\s+|x\s+)?/i, '').trim();
    s = s.replace(/\s*\([^)]*\)\s*$/, '').trim();
    s = s.replace(/,.*$/, '').trim();
    return s;
  },

  async prefetchShoppingSuggestions(force = false) {
    if (this.state.ingredientSuggestions && !force) return;
    try {
      const res = await fetch('/api/shopping/suggestions' + (force ? '?refresh=1' : ''));
      if (res.ok) {
        const data = await res.json();
        this.state.ingredientSuggestions = data.suggestions || [];
      }
    } catch (e) {
      console.warn('Failed to prefetch ingredient suggestions:', e);
    }
  },

  async openIngredientPickerModal() {
    const modal = document.getElementById('ingredient-picker-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    this.setModalOpen(true);

    const input = document.getElementById('ingredient-picker-input');
    if (input) {
      input.value = '';
      setTimeout(() => {
        try {
          input.focus({ preventScroll: true });
        } catch (e) {
          input.focus();
        }
        this.updateVisualViewport();
      }, 30);
    }

    if (!this.state.ingredientSuggestions) {
      await this.prefetchShoppingSuggestions();
    }
    this.renderIngredientSuggestions('');
  },

  closeIngredientPickerModal() {
    const modal = document.getElementById('ingredient-picker-modal');
    if (modal && modal.style.display !== 'none') {
      modal.style.display = 'none';
      this.setModalOpen(false);
    }
    const input = document.getElementById('ingredient-picker-input');
    if (input) input.value = '';
  },

  renderIngredientSuggestions(query = '') {
    const listEl = document.getElementById('ingredient-suggestions-list');
    const labelEl = document.getElementById('ingredient-suggestions-label');
    const countEl = document.getElementById('ingredient-suggestions-count');
    if (!listEl) return;

    const all = this.state.ingredientSuggestions || [];
    const q = (query || '').trim().toLowerCase();

    // Determine items already on active shopping list
    const activeItems = (this.state.currentShoppingData?.items || []).filter(i => !i.done);
    const activeCleanSet = new Set(
      activeItems.map(i => this.cleanItemName(i.text).toLowerCase()).filter(Boolean)
    );

    let filtered = [];
    if (!q) {
      if (labelEl) labelEl.textContent = 'Popular Suggestions';
      filtered = all.slice(0, 40);
    } else {
      if (labelEl) labelEl.textContent = `Matching "${query.trim()}"`;
      const startsWith = [];
      const contains = [];
      for (const item of all) {
        const name = (typeof item === 'string' ? item : item.name) || '';
        const lower = name.toLowerCase();
        if (lower.startsWith(q)) {
          startsWith.push(item);
        } else if (lower.includes(q)) {
          contains.push(item);
        }
      }
      filtered = [...startsWith, ...contains];
    }

    if (countEl) {
      countEl.textContent = `${filtered.length} found`;
    }

    listEl.innerHTML = '';

    if (filtered.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'ingredient-empty-suggestions';
      empty.innerHTML = `No matching saved suggestions.<br><span style="font-size:0.8rem; color:var(--text-secondary); margin-top:0.3rem; display:inline-block;">Press <strong>Enter</strong> or click <strong>Add</strong> to add "${query.trim()}" to shopping list.</span>`;
      listEl.appendChild(empty);
      return;
    }

    filtered.forEach(item => {
      const name = (typeof item === 'string' ? item : item.name) || '';
      const category = (typeof item === 'object' ? item.category : '') || '';
      const lower = name.toLowerCase();

      // Check if item is already on active shopping list
      const isOnList = activeCleanSet.has(lower) ||
                       activeItems.some(i => {
                         const rawLower = (i.text || '').toLowerCase();
                         const cleanLower = this.cleanItemName(i.text).toLowerCase();
                         return rawLower === lower || cleanLower === lower || rawLower.includes(lower);
                       });

      const row = document.createElement('div');
      row.className = `ingredient-suggestion-item ${isOnList ? 'already-on-list' : ''}`;
      row.setAttribute('role', 'button');
      row.setAttribute('tabindex', '0');

      let nameHtml = `<span class="ingredient-suggestion-name">${name}</span>`;
      if (isOnList) {
        nameHtml += ` <span class="already-on-list-badge">(already on list)</span>`;
      }

      let metaHtml = '';
      if (category && category.toLowerCase() !== 'general') {
        metaHtml += `<span class="ingredient-category-tag">${category}</span>`;
      }

      row.innerHTML = `
        <div class="ingredient-suggestion-main">${nameHtml}</div>
        <div class="ingredient-suggestion-meta">${metaHtml}</div>
      `;

      row.addEventListener('click', async () => {
        await this.selectIngredientSuggestion(item, isOnList);
      });

      row.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          await this.selectIngredientSuggestion(item, isOnList);
        }
      });

      listEl.appendChild(row);
    });
  },

  async selectIngredientSuggestion(item, wasAlreadyOnList = false) {
    const name = (typeof item === 'string' ? item : item.name) || '';
    const category = (typeof item === 'object' ? item.category : '') || undefined;
    if (!name) return;

    try {
      await fetch('/api/shopping/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: name,
          category: (category && category.toLowerCase() !== 'general') ? category : undefined
        })
      });
      this.closeIngredientPickerModal();
      await this.loadSpecialShoppingUI();
      this.syncCurrentFileContent();
      if (wasAlreadyOnList) {
        this.showToast(`"${name}" is already on list, added again!`, 'info');
      } else {
        this.showToast(`Added "${name}" to shopping list`, 'success');
      }
    } catch (e) {
      this.showToast('Failed to add ingredient', 'info');
    }
  },

  async submitIngredientPickerInput() {
    const input = document.getElementById('ingredient-picker-input');
    const text = input ? input.value.trim() : '';
    if (!text) return;

    // Check if free text matches any suggestion to preserve category
    let category = undefined;
    if (this.state.ingredientSuggestions) {
      const match = this.state.ingredientSuggestions.find(s => {
        const sName = typeof s === 'string' ? s : s.name;
        return sName.toLowerCase() === text.toLowerCase();
      });
      if (match && typeof match === 'object' && match.category && match.category.toLowerCase() !== 'general') {
        category = match.category;
      }
    }

    try {
      await fetch('/api/shopping/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, category })
      });
      this.closeIngredientPickerModal();
      await this.loadSpecialShoppingUI();
      this.syncCurrentFileContent();
      this.showToast(`Added "${text}" to shopping list`, 'success');
    } catch (e) {
      this.showToast('Failed to add item', 'info');
    }
  },

  // ===== Special Recipe UI =====
  async loadSpecialRecipeUI(path) {
    try {
      const res = await fetch(`/api/recipe?path=${encodeURIComponent(path)}`);
      const data = await res.json();

      document.getElementById('recipe-title').textContent = data.title || 'Recipe';

      const metaDiv = document.getElementById('recipe-meta');
      metaDiv.innerHTML = '';
      if (data.metadata) {
        Object.entries(data.metadata).forEach(([k, v]) => {
          const span = document.createElement('span');
          span.className = 'recipe-tag';
          span.textContent = `${k}: ${v}`;
          metaDiv.appendChild(span);
        });
      }

      // Ingredients (clickable to add to shopping list!)
      const ingDiv = document.getElementById('recipe-ingredients');
      ingDiv.innerHTML = '';

      const hasCategories = Array.isArray(data.ingredient_categories) &&
        data.ingredient_categories.length > 0 &&
        data.ingredient_categories.some(cat => cat.name);

      if (hasCategories) {
        data.ingredient_categories.forEach(cat => {
          if (!cat.items || cat.items.length === 0) return;

          const groupDiv = document.createElement('div');
          groupDiv.className = 'recipe-category-group';
          groupDiv.style.marginBottom = '1rem';

          if (cat.name) {
            const headerDiv = document.createElement('div');
            headerDiv.style.display = 'flex';
            headerDiv.style.justifyContent = 'space-between';
            headerDiv.style.alignItems = 'center';
            headerDiv.style.margin = '0.75rem 0 0.4rem 0';
            headerDiv.style.paddingBottom = '0.25rem';
            headerDiv.style.borderBottom = '1px solid var(--border-color)';

            const titleSpan = document.createElement('span');
            titleSpan.style.fontSize = '0.85rem';
            titleSpan.style.fontWeight = '700';
            titleSpan.style.color = 'var(--accent)';
            titleSpan.style.textTransform = 'uppercase';
            titleSpan.style.letterSpacing = '0.05em';
            titleSpan.textContent = `🏷️ ${cat.name}`;
            headerDiv.appendChild(titleSpan);

            const addCatBtn = document.createElement('button');
            addCatBtn.className = 'action-pill-btn';
            addCatBtn.style.fontSize = '0.75rem';
            addCatBtn.style.padding = '0.2rem 0.55rem';
            addCatBtn.textContent = '+ Add Section';
            addCatBtn.onclick = async (e) => {
              e.stopPropagation();
              let count = 0;
              for (const ing of cat.items) {
                const itemText = ing.text || ing.clean_name;
                if (itemText) {
                  await fetch('/api/shopping/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: itemText })
                  });
                  count++;
                }
              }
              this.showToast(`Added ${count} items from ${cat.name} to shopping list!`, 'success');
              this.loadDashboardData();
            };
            headerDiv.appendChild(addCatBtn);
            groupDiv.appendChild(headerDiv);
          }

          const itemsList = document.createElement('div');
          itemsList.className = 'ingredients-list';
          itemsList.style.gap = '0.4rem';

          cat.items.forEach(ing => {
            const item = document.createElement('div');
            item.className = 'ingredient-clickable';
            item.dataset.ingredientText = ing.text;
            item.innerHTML = `
              <span class="ingredient-name">• ${this.escapeHtml(ing.text)}</span>
              <span class="add-hint">+ Add to Shopping List</span>
            `;
            item.onclick = async () => {
              await this.addIngredientToShopping(ing.text);
            };
            itemsList.appendChild(item);
          });

          groupDiv.appendChild(itemsList);
          ingDiv.appendChild(groupDiv);
        });
      } else {
        (data.ingredients || []).forEach(ing => {
          const item = document.createElement('div');
          item.className = 'ingredient-clickable';
          item.dataset.ingredientText = ing.text;
          item.innerHTML = `
            <span class="ingredient-name">• ${this.escapeHtml(ing.text)}</span>
            <span class="add-hint">+ Add to Shopping List</span>
          `;
          item.onclick = async () => {
            await this.addIngredientToShopping(ing.text);
          };
          ingDiv.appendChild(item);
        });
      }

      // Instructions
      const instDiv = document.getElementById('recipe-instructions');
      instDiv.innerHTML = '';
      (data.instructions || []).forEach((step, idx) => {
        const stepCard = document.createElement('div');
        stepCard.className = 'step-card';
        stepCard.innerHTML = `
          <div class="step-num">${idx + 1}.</div>
          <div>${step}</div>
        `;
        instDiv.appendChild(stepCard);
      });

    } catch (e) {
      console.error('Error loading recipe UI:', e);
    }
  },

  async addIngredientToShopping(ingredientText) {
    try {
      await fetch('/api/shopping/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: ingredientText })
      });
      this.loadDashboardData();
      this.showToast(`Added "${ingredientText}" to shopping list`, 'success', [
        {
          label: 'Go to list',
          primary: false,
          onClick: () => this.openFile('shopping/list.md')
        },
        {
          label: 'Undo',
          primary: true,
          onClick: async () => {
            try {
              await fetch('/api/shopping/remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: ingredientText })
              });
              this.loadDashboardData();
              this.showToast(`Removed "${ingredientText}" from shopping list`, 'info');
            } catch (err) {
              this.showToast('Failed to undo: ' + err.message, 'info');
            }
          }
        }
      ]);
    } catch (e) {
      this.showToast('Failed to add ingredient: ' + e.message, 'info');
    }
  },

  async addAllIngredientsToShopping() {
    const ingredientEls = document.querySelectorAll('#recipe-ingredients .ingredient-clickable');
    let count = 0;
    for (const el of ingredientEls) {
      const text = el.dataset.ingredientText || el.querySelector('.ingredient-name, span:first-child')?.textContent.replace(/^•\s*/, '').trim();
      if (text) {
        await fetch('/api/shopping/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        count++;
      }
    }
    this.showToast(`Added ${count} ingredients to shopping list!`, 'success', [
      {
        label: 'Go to list',
        primary: true,
        onClick: () => this.openFile('shopping/list.md')
      }
    ]);
    this.loadDashboardData();
  },

  async addRecipeIngredientsViaAI() {
    const title = document.getElementById('recipe-title')?.textContent || 'this recipe';
    const promptText = `Please read the ingredients from this recipe (${title} at ${this.state.currentFilePath}) and add all required items to shopping/list.md, grouping them cleanly into appropriate categories.`;
    
    this.openFileAssistantModal();
    const input = document.getElementById('file-chat-input');
    if (input) input.value = promptText;

    // Send AI prompt and execute
    await this.sendChatPrompt(promptText, 'file-chat-messages', this.state.currentFilePath, this.state.currentFileContent);
    if (input) input.value = '';
  },


  // ===== Special Meal Plan UI =====
  async loadSpecialMealplanUI(path) {
    try {
      const res = await fetch(`/api/mealplan?path=${encodeURIComponent(path)}`);
      const data = await res.json();
      document.getElementById('mealplan-title').textContent = data.title || 'Weekly Meal Plan';
      const grid = document.getElementById('mealplan-days-grid');
      grid.innerHTML = '';

      (data.days || []).forEach(d => {
        const card = document.createElement('div');
        card.className = 'dash-card';
        card.innerHTML = `
          <div class="card-title" style="color: var(--accent); border-bottom: 1px solid var(--border-color); padding-bottom: 0.4rem;">
            ${d.day}
          </div>
          <div style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.5rem;">
            ${(d.meals || []).map(m => `
              <div>
                <strong>${m.recipe_link ? `<a href="javascript:App.handleLinkClick('${this.normalizeFilePath(m.recipe_link, path)}')">${m.dish}</a>` : m.dish}</strong>
                ${m.hints ? `<div style="font-size: 0.8rem; color: var(--text-muted);">${m.hints}</div>` : ''}
              </div>
            `).join('')}
          </div>
        `;
        grid.appendChild(card);
      });
    } catch (e) {
      console.error('Error loading mealplan UI:', e);
    }
  },

  // ===== Special TODO UI =====
  async loadSpecialTodoUI() {
    const listDiv = document.getElementById('special-todo-items');
    if (!listDiv) return;
    try {
      const res = await fetch('/api/todo');
      const data = await res.json();
      listDiv.innerHTML = '';

      const activeItems = (data.items || []).filter(i => !i.done);
      const doneItems = (data.items || []).filter(i => i.done);

      if (activeItems.length === 0 && doneItems.length === 0) {
        listDiv.innerHTML = '<em>Todo list is empty!</em>';
        return;
      }

      activeItems.forEach(item => {
        listDiv.appendChild(this.createTodoItemRow(item));
      });

      if (doneItems.length > 0) {
        const completedHeader = document.createElement('div');
        completedHeader.className = 'category-header';
        completedHeader.textContent = 'Completed';
        listDiv.appendChild(completedHeader);

        doneItems.forEach(item => {
          listDiv.appendChild(this.createTodoItemRow(item));
        });
      }
    } catch (e) {
      console.error('Error loading todo UI:', e);
    }
  },

  createTodoItemRow(item) {
    const row = document.createElement('div');
    row.className = `item-row ${item.done ? 'done' : ''}`;
    row.innerHTML = `
      <input type="checkbox" class="item-checkbox" ${item.done ? 'checked' : ''}>
      <span class="item-text">${item.text}</span>
      <button class="item-delete-btn" title="Remove task">✕</button>
    `;

    const chk = row.querySelector('.item-checkbox');
    chk.addEventListener('change', async (e) => {
      e.stopPropagation();
      await this.toggleTodoItem(item.id || item.text);
    });

    row.addEventListener('click', async (e) => {
      if (e.target !== chk && !e.target.classList.contains('item-delete-btn')) {
        await this.toggleTodoItem(item.id || item.text);
      }
    });

    row.querySelector('.item-delete-btn').addEventListener('click', async (e) => {
      e.stopPropagation();
      await this.removeTodoItem(item.id || item.text);
    });

    return row;
  },

  async toggleTodoItem(itemId) {
    try {
      await fetch('/api/todo/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: itemId })
      });
      await this.loadSpecialTodoUI();
      this.syncCurrentFileContent();
    } catch (e) {
      this.showToast('Toggle failed', 'info');
    }
  },

  async addTodoItem() {
    const input = document.getElementById('add-todo-input');
    const text = input ? input.value.trim() : '';
    if (!text) return;

    try {
      await fetch('/api/todo/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      input.value = '';
      await this.loadSpecialTodoUI();
      this.syncCurrentFileContent();
      this.showToast(`Added task: "${text}"`, 'success');
    } catch (e) {
      this.showToast('Failed to add task', 'info');
    }
  },

  async removeTodoItem(itemId) {
    try {
      await fetch('/api/todo/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: itemId })
      });
      await this.loadSpecialTodoUI();
      this.syncCurrentFileContent();
    } catch (e) {
      this.showToast('Failed to remove task', 'info');
    }
  },

  // ===== Special Calendar UI =====
  async loadSpecialCalendarUI() {
    const eventsDiv = document.getElementById('special-calendar-events');
    if (!eventsDiv) return;
    try {
      const res = await fetch('/api/calendar');
      const data = await res.json();
      if (data.ics_url) this.state.calendarIcsUrl = data.ics_url;
      eventsDiv.innerHTML = '';
      const events = data.events || [];

      if (events.length === 0) {
        eventsDiv.innerHTML = '<em>No calendar events found. Click "+ Add Event" to schedule one!</em>';
        return;
      }

      events.forEach(ev => {
        const card = document.createElement('div');
        card.className = 'event-card';
        card.innerHTML = `
          <div class="event-card-header">
            <div class="event-title">${this.escapeHtml(ev.summary || 'Untitled Event')}</div>
            <button class="item-delete-btn event-delete-btn" title="Delete event" aria-label="Delete event">🗑</button>
          </div>
          <div class="event-details">
            <span>🕒 ${this.escapeHtml(ev.start_str || 'TBD')} ${ev.end_str ? ' - ' + this.escapeHtml(ev.end_str) : ''}</span>
            ${ev.location ? `<span>📍 ${this.escapeHtml(ev.location)}</span>` : ''}
            ${ev.source_file ? `<span style="color: var(--text-muted); font-size: 0.75rem;">(${this.escapeHtml(ev.source_file)})</span>` : ''}
          </div>
          ${ev.description ? `<div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem;">${this.escapeHtml(ev.description)}</div>` : ''}
        `;

        const delBtn = card.querySelector('.event-delete-btn');
        if (delBtn) {
          delBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            await this.deleteCalendarEvent(ev);
          });
        }

        eventsDiv.appendChild(card);
      });
    } catch (e) {
      console.error('Error loading calendar UI:', e);
    }
  },

  showAddEventModal() {
    const modal = document.getElementById('event-modal');
    if (modal) {
      modal.style.display = 'flex';
      this.setModalOpen(true);
    }
  },

  closeAddEventModal() {
    const modal = document.getElementById('event-modal');
    if (modal && modal.style.display !== 'none') {
      modal.style.display = 'none';
      this.setModalOpen(false);
    }
  },

  async submitAddEvent() {
    const title = document.getElementById('modal-ev-title').value.trim();
    const start = document.getElementById('modal-ev-start').value;
    const loc = document.getElementById('modal-ev-loc').value.trim();
    const desc = document.getElementById('modal-ev-desc').value.trim();

    if (!title || !start) {
      alert('Event title and start date/time are required.');
      return;
    }

    try {
      const res = await fetch('/api/calendar/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          summary: title,
          start: start,
          location: loc,
          description: desc
        })
      });
      const data = await res.json();
      if (data.success) {
        this.closeAddEventModal();
        this.showToast(`Scheduled event: ${title}`, 'success');
        await this.loadSpecialCalendarUI();
        this.loadDashboardData();
        this.loadFiles();
      }
    } catch (e) {
      this.showToast('Failed to add event', 'info');
    }
  },

  async deleteCalendarEvent(ev) {
    const title = ev.summary || 'this event';
    if (!window.confirm(`Delete calendar event "${title}"?`)) return;

    try {
      const res = await fetch('/api/calendar/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uid: ev.uid,
          file: ev.source_file,
          summary: ev.summary
        })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.showToast(`Deleted event: ${title}`, 'success');
        await this.loadSpecialCalendarUI();
        this.loadDashboardData();
        await this.loadFiles();
        if (this.state.currentFilePath && (this.state.currentFilePath.startsWith('calendar/') || this.state.currentFilePath === ev.source_file)) {
          const fileStillExists = this.state.files.some(f => f.path === this.state.currentFilePath);
          if (fileStillExists) {
            this.syncCurrentFileContent();
          } else {
            const fallbackCal = this.state.files.find(f => f.type === 'calendar');
            if (fallbackCal) {
              this.openFile(fallbackCal.path);
            } else {
              this.showOverview();
            }
          }
        }
      } else {
        this.showToast(data.error || 'Failed to delete event', 'info');
      }
    } catch (e) {
      this.showToast('Failed to delete event', 'info');
    }
  },

  copyCalendarIcsUrl() {
    const icsPath = this.state.calendarIcsUrl || '/cal/60809c9cfb92adb9fe7693b32e23d9e8892925afada35d4a/calendar.ics';
    const fullUrl = window.location.origin + icsPath;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(fullUrl).then(() => {
        this.showToast('Calendar .ics subscription URL copied to clipboard!', 'success');
      }).catch(() => {
        prompt('Copy calendar .ics subscription URL:', fullUrl);
      });
    } else {
      prompt('Copy calendar .ics subscription URL:', fullUrl);
    }
  },

  // ===== Synchronize File Content =====
  async syncCurrentFileContent() {
    if (!this.state.currentFilePath) return;
    try {
      const res = await fetch(`/api/file?path=${encodeURIComponent(this.state.currentFilePath)}`);
      const data = await res.json();
      this.state.currentFileContent = data.content;
      const rawTextarea = document.getElementById('raw-editor-text');
      if (rawTextarea) rawTextarea.value = data.content;
      this.renderWYSIWYG(data.content);
    } catch (e) {
      console.error('Error syncing file:', e);
    }
  },

  async saveCurrentFile() {
    if (!this.state.currentFilePath) return;
    const rawTextarea = document.getElementById('raw-editor-text');
    const content = (this.state.currentTab === 'raw' && rawTextarea)
      ? rawTextarea.value
      : this.state.currentFileContent;

    try {
      const res = await fetch('/api/file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: this.state.currentFilePath,
          content: content
        })
      });
      const data = await res.json();
      if (data.success) {
        this.state.currentFileContent = content;
        if (rawTextarea) rawTextarea.value = content;
        this.renderWYSIWYG(content);
        this.showToast('File saved successfully', 'success');
        this.checkGitStatus();
        this.loadDashboardData();
        if (['shopping', 'recipe', 'mealplan', 'todo', 'calendar'].includes(this.state.currentFileType)) {
          this.renderSpecialView(this.state.currentFileType, this.state.currentFilePath, content);
        }
      }
    } catch (e) {
      this.showToast('Save failed: ' + e.message, 'info');
    }
  },

  promptNewFile() {
    const name = prompt('Enter new file path (e.g. notes/vacation.md or shopping/recipes/pasta.md):');
    if (!name) return;
    fetch('/api/file/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: name, content: `# ${name.split('/').pop().replace('.md', '')}\n\n` })
    }).then(r => r.json()).then(data => {
      if (data.success) {
        this.loadFiles();
        this.openFile(name);
      }
    });
  },

  promptNewFileInCurrentFolder() {
    const folder = this.state.currentFolderPath || 'shopping';
    const filename = prompt(`Create new markdown file in ${folder}/:`, 'new-item.md');
    if (!filename) return;
    const cleanName = filename.endsWith('.md') ? filename : `${filename}.md`;
    const fullPath = `${folder}/${cleanName}`;
    fetch('/api/file/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: fullPath, content: `# ${cleanName.replace('.md', '')}\n\n` })
    }).then(r => r.json()).then(data => {
      if (data.success) {
        this.loadFiles();
        this.openFile(fullPath);
      }
    });
  },

  openFolder(folderPath, push = true) {
    this.state.currentView = 'folder';
    this.state.currentFolderPath = folderPath;
    this.state.currentFilePath = null;
    this.state.currentFileType = 'folder';

    document.getElementById('view-overview').style.display = 'none';
    document.getElementById('view-editor').style.display = 'flex';

    if (push) {
      const newUrl = `${window.location.pathname}?folder=${encodeURIComponent(folderPath)}`;
      if (window.location.search !== `?folder=${encodeURIComponent(folderPath)}`) {
        history.pushState({ view: 'folder', folder: folderPath }, '', newUrl);
      }
    }

    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    this.renderPathBreadcrumbs(folderPath, true);
    const ctxBadge = document.getElementById('file-chat-context-badge');
    if (ctxBadge) ctxBadge.textContent = `Folder: ${folderPath}/`;

    const badge = document.getElementById('editor-mode-badge');
    if (badge) badge.textContent = 'Folder';

    this.updateBurgerMenuState();
    this.switchEditorTab('special');
    this.renderSpecialView('folder', folderPath, '');
  },

  renderPathBreadcrumbs(path, isFolder = false) {
    const el = document.getElementById('editor-current-path');
    if (!el) return;

    const cleanPath = (path || '').trim().replace(/^\/+/, '').replace(/\/+$/, '');
    if (!cleanPath) {
      el.textContent = '';
      return;
    }

    const parts = cleanPath.split('/');
    let accum = '';
    let html = '';

    parts.forEach((part, idx) => {
      accum += (accum ? '/' : '') + part;
      const currentAccum = accum;
      const isLast = idx === parts.length - 1;

      if (idx > 0) {
        html += `<span class="path-separator">/</span>`;
      }

      if (isLast && !isFolder) {
        html += `<span class="path-segment path-file" onclick="App.openFile('${currentAccum}')" title="File: ${currentAccum}">${part}</span>`;
      } else {
        html += `<span class="path-segment path-folder" onclick="App.openFolder('${currentAccum}')" title="Go to folder: ${currentAccum}">${part}</span>`;
      }
    });

    if (isFolder) {
      html += `<span class="path-separator">/</span>`;
    }

    el.innerHTML = html;
  },

  renderFolderContents(folderPath) {
    const breadcrumbs = document.getElementById('folder-view-breadcrumbs');
    const grid = document.getElementById('folder-view-items');
    if (!breadcrumbs || !grid) return;

    // Build breadcrumbs
    const parts = folderPath.split('/').filter(Boolean);
    let breadcrumbsHtml = `<span style="cursor: pointer; color: var(--accent);" onclick="App.showOverview()">🏠 Overview</span>`;
    let accum = '';
    parts.forEach((p, idx) => {
      accum += (accum ? '/' : '') + p;
      const currentAccum = accum;
      breadcrumbsHtml += ` <span style="color: var(--text-muted);">/</span> `;
      if (idx === parts.length - 1) {
        breadcrumbsHtml += `<span style="color: var(--text-primary);">${p}</span>`;
      } else {
        breadcrumbsHtml += `<span style="cursor: pointer; color: var(--accent);" onclick="App.openFolder('${currentAccum}')">${p}</span>`;
      }
    });
    breadcrumbs.innerHTML = breadcrumbsHtml;

    // Filter files and immediate subdirectories in this folder
    const prefix = folderPath.endsWith('/') ? folderPath : `${folderPath}/`;
    const subfolderMap = new Map();
    const directFiles = [];

    this.state.files.forEach(f => {
      if (f.path.startsWith(prefix)) {
        const rel = f.path.substring(prefix.length);
        const relParts = rel.split('/');
        if (relParts.length > 1) {
          const subDirName = relParts[0];
          const subDirPath = `${folderPath}/${subDirName}`;
          if (!subfolderMap.has(subDirName)) {
            subfolderMap.set(subDirName, { name: subDirName, path: subDirPath, count: 1 });
          } else {
            subfolderMap.get(subDirName).count++;
          }
        } else {
          directFiles.push(f);
        }
      }
    });

    grid.innerHTML = '';

    // Render Parent Folder row if not root
    if (parts.length > 1) {
      const parentPath = parts.slice(0, -1).join('/');
      const parentRow = document.createElement('div');
      parentRow.className = 'folder-list-row parent-row';
      parentRow.innerHTML = `
        <span class="folder-list-name">..</span>
        <span class="folder-list-meta">Up to ${parentPath}/</span>
      `;
      parentRow.onclick = () => this.openFolder(parentPath);
      grid.appendChild(parentRow);
    }

    const subfolders = Array.from(subfolderMap.values()).sort((a, b) => a.name.localeCompare(b.name));
    const sortedDirectFiles = directFiles.sort((a, b) => a.name.localeCompare(b.name));

    // 1. Folders Section
    if (subfolders.length > 0) {
      const folderHeader = document.createElement('div');
      folderHeader.className = 'folder-list-section-title';
      folderHeader.textContent = 'Folders';
      grid.appendChild(folderHeader);

      subfolders.forEach(sub => {
        const row = document.createElement('div');
        row.className = 'folder-list-row is-folder';
        row.innerHTML = `
          <span class="folder-list-name">${sub.name}/</span>
          <span class="folder-list-meta">${sub.count} ${sub.count === 1 ? 'file' : 'files'}</span>
        `;
        row.onclick = () => this.openFolder(sub.path);
        grid.appendChild(row);
      });
    }

    // 2. Files Section
    if (sortedDirectFiles.length > 0) {
      const fileHeader = document.createElement('div');
      fileHeader.className = 'folder-list-section-title';
      fileHeader.textContent = 'Files';
      grid.appendChild(fileHeader);

      sortedDirectFiles.forEach(file => {
        const row = document.createElement('div');
        row.className = 'folder-list-row';
        row.innerHTML = `
          <span class="folder-list-name">${file.name}</span>
          <span class="folder-list-meta">${file.type || 'file'}</span>
        `;
        row.onclick = () => this.openFile(file.path);
        grid.appendChild(row);
      });
    }

    if (subfolders.length === 0 && sortedDirectFiles.length === 0) {
      grid.innerHTML = '<div style="color: var(--text-muted); padding: 1.5rem; font-style: italic;">This folder is empty.</div>';
    }
  },


  // ===== AI Chat Handlers =====
  async handleOverviewChatSubmit(e) {
    e.preventDefault();
    const input = document.getElementById('overview-chat-input');
    const prompt = input.value.trim();
    if (!prompt) return;
    input.value = '';
    await this.sendChatPrompt(prompt, 'overview-chat-messages');
  },

  async sendOverviewPrompt(promptText) {
    const input = document.getElementById('overview-chat-input');
    if (input) input.value = promptText;
    await this.sendChatPrompt(promptText, 'overview-chat-messages');
    if (input) input.value = '';
  },

  // ===== Burger Menu & Assistant Modal =====
  toggleBurgerMenu() {
    const drawer = document.getElementById('burger-drawer');
    if (!drawer) return;
    if (drawer.classList.contains('open')) {
      this.closeBurgerMenu();
    } else {
      this.openBurgerMenu();
    }
  },

  openBurgerMenu() {
    const drawer = document.getElementById('burger-drawer');
    const overlay = document.getElementById('burger-overlay');
    this.updateBurgerMenuState();
    if (overlay) overlay.classList.add('open');
    if (drawer) drawer.classList.add('open');
  },

  closeBurgerMenu() {
    const drawer = document.getElementById('burger-drawer');
    const overlay = document.getElementById('burger-overlay');
    if (overlay) overlay.classList.remove('open');
    if (drawer) drawer.classList.remove('open');
  },

  updateBurgerMenuState() {
    const isFileView = (this.state.currentView === 'editor' && !!this.state.currentFilePath);
    const modeSection = document.getElementById('burger-mode-section');
    const fileSection = document.getElementById('burger-file-section');
    const subTitle = document.getElementById('burger-assistant-subtitle');
    const deleteSub = document.getElementById('burger-delete-sub');

    if (isFileView) {
      if (modeSection) modeSection.style.display = 'block';
      if (fileSection) fileSection.style.display = 'block';
      const baseName = this.state.currentFilePath.split('/').pop();
      if (subTitle) subTitle.textContent = `Ask about ${baseName}`;
      if (deleteSub) deleteSub.textContent = `Remove ${baseName}`;

      const isSpecial = ['shopping', 'recipe', 'mealplan', 'todo', 'calendar'].includes(this.state.currentFileType);
      const btnSpecial = document.getElementById('burger-mode-special');
      const btnWysiwyg = document.getElementById('burger-mode-wysiwyg');
      const btnRaw = document.getElementById('burger-mode-raw');

      if (btnSpecial) {
        btnSpecial.style.display = isSpecial ? 'flex' : 'none';
        btnSpecial.classList.toggle('active', this.state.currentTab === 'special');
      }
      if (btnWysiwyg) {
        btnWysiwyg.classList.toggle('active', this.state.currentTab === 'wysiwyg');
      }
      if (btnRaw) {
        btnRaw.classList.toggle('active', this.state.currentTab === 'raw');
      }
    } else {
      if (modeSection) modeSection.style.display = 'none';
      if (fileSection) fileSection.style.display = 'none';
      if (subTitle) subTitle.textContent = 'Family Assistant';
    }
  },

  selectBurgerMode(mode) {
    this.switchEditorTab(mode);
    this.updateBurgerMenuState();
    this.closeBurgerMenu();
  },

  handleBurgerOpenAssistant() {
    this.closeBurgerMenu();
    if (this.state.currentView === 'editor' && this.state.currentFilePath) {
      this.openFileAssistantModal();
    } else {
      this.showOverview();
      setTimeout(() => {
        const chatInput = document.getElementById('overview-chat-input');
        const chatCard = document.querySelector('.ai-chat-card');
        if (chatCard) chatCard.scrollIntoView({ behavior: 'smooth' });
        if (chatInput) chatInput.focus();
      }, 100);
    }
  },

  openFileAssistantModal() {
    const modal = document.getElementById('file-assistant-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    this.setModalOpen(true);

    const ctxBadge = document.getElementById('file-chat-context-badge');
    if (ctxBadge && this.state.currentFilePath) {
      ctxBadge.textContent = `Context: ${this.state.currentFilePath}`;
    }
    const input = document.getElementById('file-chat-input');
    if (input) {
      setTimeout(() => {
        try {
          input.focus({ preventScroll: true });
        } catch (e) {
          input.focus();
        }
        this.updateVisualViewport();
        this.scrollActiveChatToBottom();
      }, 50);
    }
    // If opening the modal after completion, clear the done status
    if (this.state.aiStatus === 'done') {
      this.state.aiStatus = 'idle';
    }
    this.updateAiHeaderStatus();
  },

  closeFileAssistantModal() {
    const modal = document.getElementById('file-assistant-modal');
    if (modal && modal.style.display !== 'none') {
      modal.style.display = 'none';
      this.setModalOpen(false);
    }
    this.updateAiHeaderStatus();
  },

  updateAiHeaderStatus() {
    const btn = document.getElementById('ai-header-status-btn');
    const icon = document.getElementById('ai-header-icon');
    const text = document.getElementById('ai-header-text');
    if (!btn || !icon || !text) return;

    const modal = document.getElementById('file-assistant-modal');
    const isModalOpen = (modal && modal.style.display !== 'none');

    // Only show indicator in topmost bar when modal AI dialog is closed
    if (isModalOpen) {
      btn.style.display = 'none';
      return;
    }

    if (this.state.aiStatus === 'thinking') {
      btn.style.display = 'inline-flex';
      btn.className = 'ai-header-status-btn thinking';
      btn.title = 'AI is thinking... Click to view';
      icon.innerHTML = '<span class="ai-spinner-ring"></span>';
      text.textContent = 'Thinking...';
    } else if (this.state.aiStatus === 'done') {
      btn.style.display = 'inline-flex';
      btn.className = 'ai-header-status-btn done';
      btn.title = 'AI finished! Click to view';
      icon.innerHTML = '<span class="ai-check-icon">✓</span>';
      text.textContent = 'Done';
    } else {
      btn.style.display = 'none';
    }
  },

  handleAiHeaderStatusClick() {
    this.openFileAssistantModal();
  },

  async confirmDeleteCurrentFile() {
    const path = this.state.currentFilePath;
    if (!path) return;

    const confirmed = window.confirm(`Are you sure you want to delete "${path}"? This action cannot be undone.`);
    if (!confirmed) return;

    this.closeBurgerMenu();

    try {
      const res = await fetch('/api/file/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      const data = await res.json();
      if (data.success) {
        this.showToast(`Deleted ${path}`, 'success');
        this.state.currentFilePath = null;
        this.state.currentFileType = null;
        await this.loadFiles();
        this.showOverview(true);
      } else {
        this.showToast(`Failed to delete: ${data.error || 'Unknown error'}`, 'info');
      }
    } catch (e) {
      this.showToast(`Error deleting file: ${e.message}`, 'info');
    }
  },

  toggleFileChatCollapse() {
    // Kept for backward compatibility if invoked
    const body = document.getElementById('file-chat-body');
    const btn = document.getElementById('toggle-chat-collapse');
    if (!body || !btn) return;
    if (body.style.display === 'none') {
      body.style.display = 'block';
      btn.textContent = '▾';
    } else {
      body.style.display = 'none';
      btn.textContent = '▸';
    }
  },

  async handleFileChatSubmit(e) {
    e.preventDefault();
    const input = document.getElementById('file-chat-input');
    const prompt = input.value.trim();
    if (!prompt) return;
    input.value = '';
    await this.sendChatPrompt(prompt, 'file-chat-messages', this.state.currentFilePath, this.state.currentFileContent);
  },

  async executeSpecialAction(action) {
    this.openFileAssistantModal();

    let promptText = '';
    if (action === 'group_categories') {
      promptText = 'Please reorganize the shopping list in shopping/list.md by supermarket categories (Produce, Dairy, Pantry, Meat, Frozen, Household, etc.), keeping completed items at the bottom.';
    } else if (action === 'merge_duplicates') {
      promptText = 'Please merge duplicate items in the shopping list in shopping/list.md (combine quantities or remove duplicate mentions), keeping completed items at the bottom.';
    } else {
      promptText = action;
    }

    const input = document.getElementById('file-chat-input');
    if (input) input.value = promptText;

    // Send through chatbox so the user sees the prompt and when it's done
    await this.sendChatPrompt(promptText, 'file-chat-messages', this.state.currentFilePath, this.state.currentFileContent);
    if (input) input.value = '';
  },

  async sendChatPrompt(prompt, containerId, filePath = null, fileContent = null) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Disable inputs while running
    const isOverview = (containerId === 'overview-chat-messages');
    const sendBtn = document.getElementById(isOverview ? 'overview-chat-send-btn' : 'file-chat-send-btn');
    const inputField = document.getElementById(isOverview ? 'overview-chat-input' : 'file-chat-input');
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.textContent = 'Running...';
    }

    // Set AI status to thinking and update topmost bar indicator if dialog is closed
    this.state.aiStatus = 'thinking';
    this.updateAiHeaderStatus();

    // Append user message
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-message user';
    userMsg.innerHTML = `<div class="message-bubble">${prompt}</div>`;
    container.appendChild(userMsg);

    // Append assistant bubble with running status
    const assistantMsg = document.createElement('div');
    assistantMsg.className = 'chat-message assistant';
    assistantMsg.innerHTML = `
      <div class="message-bubble">
        <div class="message-text"><em>Thinking...</em></div>
        <div class="message-status running"><span>⏳</span> <span>Working on your request...</span></div>
      </div>
    `;
    container.appendChild(assistantMsg);
    container.scrollTop = container.scrollHeight;

    const textDiv = assistantMsg.querySelector('.message-text');
    const statusDiv = assistantMsg.querySelector('.message-status');

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt,
          file_path: filePath,
          file_content: fileContent,
          stream: true
        })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let responseText = '';
      textDiv.textContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const eventData = JSON.parse(line.substring(6));
              if (eventData.type === 'chunk') {
                responseText += eventData.text;
                textDiv.innerHTML = this.parseMarkdownToHTML(responseText);
                container.scrollTop = container.scrollHeight;
              } else if (eventData.type === 'done') {
                const modFiles = eventData.files_modified || [];
                if (statusDiv) {
                  statusDiv.className = 'message-status done';
                  if (modFiles.length > 0) {
                    statusDiv.innerHTML = `<span>✓</span> <span>Done • Updated ${modFiles.join(', ')}</span>`;
                  } else {
                    statusDiv.innerHTML = `<span>✓</span> <span>Done</span>`;
                  }
                }

                if (modFiles.length > 0) {
                  // Auto-expand folder tree for modified or created files
                  modFiles.forEach(f => {
                    const parts = f.split('/');
                    for (let i = 1; i < parts.length; i++) {
                      this.state.expandedFolders.add(parts.slice(0, i).join('/'));
                    }
                  });

                  this.showToast(`AI agent updated: ${modFiles.join(', ')}`, 'success');

                  // If current file was modified, reload editor view
                  if (this.state.currentFilePath && modFiles.includes(this.state.currentFilePath)) {
                    await this.syncCurrentFileContent();
                    if (['shopping', 'recipe', 'mealplan', 'todo', 'calendar'].includes(this.state.currentFileType)) {
                      this.renderSpecialView(this.state.currentFileType, this.state.currentFilePath, this.state.currentFileContent);
                    }
                  }
                }

                this.state.aiStatus = 'done';
                this.updateAiHeaderStatus();

                // ALWAYS reload files from filesystem, dashboard cards, recent changes, and git status
                await this.loadFiles();
                this.loadDashboardData();
                this.loadRecentChanges();
                this.checkGitStatus();
              } else if (eventData.type === 'error') {
                this.state.aiStatus = 'idle';
                this.updateAiHeaderStatus();
                if (statusDiv) {
                  statusDiv.className = 'message-status';
                  statusDiv.style.color = 'var(--danger)';
                  statusDiv.innerHTML = `<span>✕</span> <span>Error: ${eventData.error}</span>`;
                }
              }
            } catch (err) {
              // Ignore non-json chunks
            }
          }
        }
      }

      if (!responseText && statusDiv && statusDiv.className.includes('running')) {
        statusDiv.className = 'message-status done';
        statusDiv.innerHTML = `<span>✓</span> <span>Done</span>`;
      }

      if (this.state.aiStatus === 'thinking') {
        this.state.aiStatus = 'done';
        this.updateAiHeaderStatus();
      }

    } catch (e) {
      this.state.aiStatus = 'idle';
      this.updateAiHeaderStatus();
      if (statusDiv) {
        statusDiv.className = 'message-status';
        statusDiv.style.color = 'var(--danger)';
        statusDiv.innerHTML = `<span>✕</span> <span>Connection error: ${e.message}</span>`;
      }
    } finally {
      if (this.state.aiStatus === 'thinking') {
        this.state.aiStatus = 'idle';
        this.updateAiHeaderStatus();
      }
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.textContent = 'Send';
      }
      container.scrollTop = container.scrollHeight;
    }
  }
};

// Initialize App on DOM load
window.addEventListener('DOMContentLoaded', () => {
  App.init();
});
