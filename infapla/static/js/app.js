// InFaPla - Frontend Application Controller
const App = {
  state: {
    currentView: 'overview',
    currentFilePath: null,
    currentFileType: null,
    currentFileContent: '',
    currentTab: 'wysiwyg',
    files: [],
    gitDirty: false,
    expandedFolders: new Set(),
    currentDiffHash: null,
    currentDiffMessage: '',
    currentDiffRaw: '',
    diffFormat: 'side-by-side',
  },

  init() {
    this.bindEvents();
    this.refreshAll();
    // Poll git status periodically
    setInterval(() => this.checkGitStatus(), 15000);
  },

  bindEvents() {
    // Diff modal click outside or ESC to close
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.closeDiffModal();
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

    // Visual (WYSIWYG) input listener
    const wysiwygContent = document.getElementById('wysiwyg-content');
    if (wysiwygContent) {
      wysiwygContent.addEventListener('input', () => {
        // Simple text synchronization
        this.state.currentFileContent = wysiwygContent.innerText;
        if (rawEditor) rawEditor.value = this.state.currentFileContent;
      });
    }
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


  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${type === 'success' ? '✓' : 'ℹ'}</span> <span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
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
      const res = await fetch('/api/files');
      const data = await res.json();
      this.state.files = data.files || [];
      this.renderFileTree();
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
    if (modal) {
      modal.style.display = 'none';
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

    document.getElementById('editor-current-path').textContent = path;
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

      // Ensure content tabs are visible for files
      const contentTabBar = document.getElementById('content-tab-bar');
      if (contentTabBar) contentTabBar.style.display = 'flex';

      // Handle Special and Mode Tabs
      const isSpecial = ['shopping', 'recipe', 'mealplan', 'todo', 'calendar'].includes(data.type);
      const tabSpecial = document.getElementById('tab-special');
      const tabWysiwyg = document.getElementById('tab-wysiwyg');
      const tabRaw = document.getElementById('tab-raw');
      const shoppingActions = document.getElementById('shopping-special-actions');

      if (shoppingActions) {
        shoppingActions.style.display = (data.type === 'shopping') ? 'flex' : 'none';
      }

      if (tabWysiwyg) tabWysiwyg.style.display = 'inline-flex';
      if (tabRaw) tabRaw.style.display = 'inline-flex';

      if (isSpecial) {
        if (tabSpecial) {
          tabSpecial.style.display = 'inline-flex';
          tabSpecial.textContent = 'Interactive';
        }
        // Default to interactive mode for special files (shopping list, tasks, calendar, recipes, mealplan)
        this.switchEditorTab('special');
        this.renderSpecialView(data.type, path, data.content);
      } else {
        if (tabSpecial) tabSpecial.style.display = 'none';
        this.switchEditorTab('wysiwyg');
      }

    } catch (e) {
      this.showToast('Failed to open file: ' + e.message, 'info');
    }
  },

  switchEditorTab(tabName) {
    this.state.currentTab = tabName;

    const tabSpecial = document.getElementById('tab-special');
    const tabWysiwyg = document.getElementById('tab-wysiwyg');
    const tabRaw = document.getElementById('tab-raw');

    const paneSpecial = document.getElementById('pane-special');
    const paneWysiwyg = document.getElementById('pane-wysiwyg');
    const paneRaw = document.getElementById('pane-raw');

    [tabSpecial, tabWysiwyg, tabRaw].forEach(t => { if (t) t.classList.remove('active'); });
    [paneSpecial, paneWysiwyg, paneRaw].forEach(p => { if (p) p.style.display = 'none'; });

    if (tabName === 'special') {
      if (tabSpecial) tabSpecial.classList.add('active');
      if (paneSpecial) paneSpecial.style.display = 'block';
    } else if (tabName === 'raw') {
      if (tabRaw) tabRaw.classList.add('active');
      if (paneRaw) paneRaw.style.display = 'flex';
      const rawTextarea = document.getElementById('raw-editor-text');
      if (rawTextarea) rawTextarea.value = this.state.currentFileContent;
    } else {
      if (tabWysiwyg) tabWysiwyg.classList.add('active');
      if (paneWysiwyg) paneWysiwyg.style.display = 'flex';
      this.renderWYSIWYG(this.state.currentFileContent);
    }
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

    // Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/gim, '<a href="javascript:App.handleLinkClick(\'$2\')">$1</a>');

    // Paragraph breaks
    html = html.replace(/\n\n/gim, '<p></p>');

    return html;
  },

  handleLinkClick(href) {
    if (href.startsWith('http://') || href.startsWith('https://')) {
      window.open(href, '_blank');
      return;
    }
    // Relative link
    const cleanPath = href.replace(/^\.\.\//, 'shopping/').replace(/^\.\//, '');
    this.openFile(cleanPath);
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
      <button class="item-delete-btn" title="Remove item">✕</button>
    `;

    const chk = row.querySelector('.item-checkbox');
    chk.addEventListener('change', async (e) => {
      e.stopPropagation();
      await this.toggleShoppingItem(item.id || item.text);
    });

    row.addEventListener('click', async (e) => {
      if (e.target !== chk && !e.target.classList.contains('item-delete-btn')) {
        await this.toggleShoppingItem(item.id || item.text);
      }
    });

    row.querySelector('.item-delete-btn').addEventListener('click', async (e) => {
      e.stopPropagation();
      await this.removeShoppingItem(item.id || item.text);
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
    if (!text) return;

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

  async clearShoppingChecked() {
    try {
      const res = await fetch('/api/shopping/clear-completed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      await this.loadSpecialShoppingUI();
      this.syncCurrentFileContent();
      this.showToast('Cleared completed items!', 'success');
      this.loadDashboardData();
    } catch (e) {
      this.showToast('Failed to clear completed items', 'info');
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
      (data.ingredients || []).forEach(ing => {
        const item = document.createElement('div');
        item.className = 'ingredient-clickable';
        item.innerHTML = `
          <span>• ${ing.text}</span>
          <span class="add-hint">+ Add to Shopping List</span>
        `;
        item.onclick = async () => {
          await this.addIngredientToShopping(ing.clean_name || ing.text);
        };
        ingDiv.appendChild(item);
      });

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
      this.showToast(`Added "${ingredientText}" to shopping list!`, 'success');
      this.loadDashboardData();
    } catch (e) {
      this.showToast('Failed to add ingredient', 'info');
    }
  },

  async addAllIngredientsToShopping() {
    const ingredients = document.querySelectorAll('#recipe-ingredients .ingredient-clickable span:first-child');
    let count = 0;
    for (const el of ingredients) {
      const text = el.textContent.replace(/^•\s*/, '').trim();
      if (text) {
        await fetch('/api/shopping/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        count++;
      }
    }
    this.showToast(`Added ${count} ingredients to shopping list!`, 'success');
    this.loadDashboardData();
  },

  async addRecipeIngredientsViaAI() {
    const title = document.getElementById('recipe-title')?.textContent || 'this recipe';
    const promptText = `Please read the ingredients from this recipe (${title} at ${this.state.currentFilePath}) and add all required items to shopping/list.md, grouping them cleanly into appropriate categories.`;
    
    // Ensure file chat is expanded
    const body = document.getElementById('file-chat-body');
    const btn = document.getElementById('toggle-chat-collapse');
    if (body && body.style.display === 'none') {
      body.style.display = 'block';
      if (btn) btn.textContent = '▾';
    }

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
                <strong>${m.recipe_link ? `<a href="javascript:App.handleLinkClick('${m.recipe_link}')">${m.dish}</a>` : m.dish}</strong>
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
          <div class="event-title">${ev.summary}</div>
          <div class="event-details">
            <span>🕒 ${ev.start_str || 'TBD'} ${ev.end_str ? ' - ' + ev.end_str : ''}</span>
            ${ev.location ? `<span>📍 ${ev.location}</span>` : ''}
            ${ev.source_file ? `<span style="color: var(--text-muted); font-size: 0.75rem;">(${ev.source_file})</span>` : ''}
          </div>
          ${ev.description ? `<div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem;">${ev.description}</div>` : ''}
        `;
        eventsDiv.appendChild(card);
      });
    } catch (e) {
      console.error('Error loading calendar UI:', e);
    }
  },

  showAddEventModal() {
    const modal = document.getElementById('event-modal');
    if (modal) modal.style.display = 'flex';
  },

  closeAddEventModal() {
    const modal = document.getElementById('event-modal');
    if (modal) modal.style.display = 'none';
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
    const content = (this.state.currentTab === 'raw')
      ? document.getElementById('raw-editor-text').value
      : (this.state.currentTab === 'wysiwyg'
          ? this.state.currentFileContent
          : this.state.currentFileContent);

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
    document.getElementById('editor-current-path').textContent = `${folderPath}/`;
    const ctxBadge = document.getElementById('file-chat-context-badge');
    if (ctxBadge) ctxBadge.textContent = `Folder: ${folderPath}/`;

    // In folder view, hide tabs since folder view only displays directory contents
    const contentTabBar = document.getElementById('content-tab-bar');
    if (contentTabBar) contentTabBar.style.display = 'none';

    this.switchEditorTab('special');
    this.renderSpecialView('folder', folderPath, '');
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

  toggleFileChatCollapse() {
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
    // Ensure chatbox is open so user sees prompt and progress
    const body = document.getElementById('file-chat-body');
    const btn = document.getElementById('toggle-chat-collapse');
    if (body && body.style.display === 'none') {
      body.style.display = 'block';
      if (btn) btn.textContent = '▾';
    }

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
                  this.showToast(`AI agent updated: ${modFiles.join(', ')}`, 'success');
                  // If current file was modified, reload editor view
                  if (this.state.currentFilePath && modFiles.includes(this.state.currentFilePath)) {
                    await this.syncCurrentFileContent();
                    if (['shopping', 'recipe', 'mealplan', 'todo', 'calendar'].includes(this.state.currentFileType)) {
                      this.renderSpecialView(this.state.currentFileType, this.state.currentFilePath, this.state.currentFileContent);
                    }
                  }
                  this.loadDashboardData();
                  this.checkGitStatus();
                }
              } else if (eventData.type === 'error') {
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

    } catch (e) {
      if (statusDiv) {
        statusDiv.className = 'message-status';
        statusDiv.style.color = 'var(--danger)';
        statusDiv.innerHTML = `<span>✕</span> <span>Connection error: ${e.message}</span>`;
      }
    } finally {
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
