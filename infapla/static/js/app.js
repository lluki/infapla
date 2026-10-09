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
  },

  init() {
    this.bindEvents();
    this.refreshAll();
    // Poll git status periodically
    setInterval(() => this.checkGitStatus(), 15000);
  },

  bindEvents() {
    const mobileToggle = document.getElementById('mobile-toggle');
    const sidebar = document.getElementById('app-sidebar');
    if (mobileToggle && sidebar) {
      mobileToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
      });
    }

    // Sync raw editor changes to state
    const rawEditor = document.getElementById('raw-editor-text');
    if (rawEditor) {
      rawEditor.addEventListener('input', (e) => {
        this.state.currentFileContent = e.target.value;
      });
    }

    // WYSIWYG input listener
    const wysiwygPane = document.getElementById('pane-wysiwyg');
    if (wysiwygPane) {
      wysiwygPane.addEventListener('input', () => {
        // Simple text synchronization
        this.state.currentFileContent = wysiwygPane.innerText;
        if (rawEditor) rawEditor.value = this.state.currentFileContent;
      });
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
      this.loadGitHistory(),
      this.checkGitStatus(),
      this.loadAppInfo()
    ]);
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

  renderFileTree() {
    const list = document.getElementById('file-tree-list');
    if (!list) return;
    list.innerHTML = '';

    const iconMap = {
      shopping: '🛒',
      recipe: '🍲',
      mealplan: '📋',
      todo: '✅',
      calendar: '📅',
      markdown: '📝',
      generic: '📄'
    };

    this.state.files.forEach(f => {
      const li = document.createElement('li');
      li.className = `file-tree-item ${this.state.currentFilePath === f.path ? 'active' : ''}`;
      const isSpecial = ['shopping', 'recipe', 'mealplan', 'todo', 'calendar'].includes(f.type);
      if (isSpecial) li.classList.add('special-folder');

      const icon = iconMap[f.type] || '📄';
      li.innerHTML = `
        <span>${icon}</span>
        <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${f.path}</span>
      `;
      li.onclick = () => {
        const sidebar = document.getElementById('app-sidebar');
        if (sidebar) sidebar.classList.remove('open');
        this.openFile(f.path);
      };
      list.appendChild(li);
    });
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

  async loadGitHistory() {
    try {
      const res = await fetch('/api/git/history?limit=10');
      const data = await res.json();
      const list = document.getElementById('git-history-list');
      if (!list) return;
      list.innerHTML = '';
      (data.commits || []).forEach(c => {
        const li = document.createElement('li');
        li.className = 'file-tree-item';
        li.style.flexDirection = 'column';
        li.style.alignItems = 'flex-start';
        li.innerHTML = `
          <div style="font-weight: 600; color: var(--text-primary); font-size: 0.75rem;">${c.message}</div>
          <div style="color: var(--text-muted); font-size: 0.7rem;">${c.short_hash} • ${c.date}</div>
        `;
        list.appendChild(li);
      });
    } catch (e) {
      console.error('Git history load error:', e);
    }
  },

  async checkGitStatus() {
    try {
      const res = await fetch('/api/git/status');
      const data = await res.json();
      this.state.gitDirty = data.dirty;
      const badge = document.getElementById('git-status-badge');
      if (badge) {
        if (data.dirty) {
          badge.className = 'status-badge dirty';
          badge.textContent = `Git: ${data.changed_files.length} changed`;
        } else {
          badge.className = 'status-badge clean';
          badge.textContent = 'Git: Synced';
        }
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

  showOverview() {
    this.state.currentView = 'overview';
    this.state.currentFilePath = null;
    document.getElementById('view-overview').style.display = 'flex';
    document.getElementById('view-editor').style.display = 'none';
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('nav-overview').classList.add('active');
    this.renderFileTree();
    this.loadDashboardData();
  },

  openCalendarView() {
    const calFile = this.state.files.find(f => f.type === 'calendar');
    this.openFile(calFile ? calFile.path : 'calendar/family.ics');
  },

  async openFile(path) {
    this.state.currentView = 'editor';
    this.state.currentFilePath = path;
    document.getElementById('view-overview').style.display = 'none';
    document.getElementById('view-editor').style.display = 'flex';

    document.getElementById('editor-current-path').textContent = path;
    const ctxBadge = document.getElementById('file-chat-context-badge');
    if (ctxBadge) ctxBadge.textContent = `Context: ${path}`;

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

      // Handle Special Folder View Tab
      const isSpecial = ['shopping', 'recipe', 'mealplan', 'todo', 'calendar'].includes(data.type);
      const tabSpecial = document.getElementById('tab-special');
      const shoppingActions = document.getElementById('shopping-special-actions');

      if (shoppingActions) {
        shoppingActions.style.display = (data.type === 'shopping') ? 'flex' : 'none';
      }

      if (isSpecial) {
        tabSpecial.style.display = 'inline-block';
        const labels = {
          shopping: '🛒 Interactive Shopping List',
          recipe: '🍲 Recipe View',
          mealplan: '📋 Meal Planner',
          todo: '✅ Interactive Tasks',
          calendar: '📅 Family Schedule'
        };
        tabSpecial.textContent = labels[data.type] || 'Special View';
        // Default to interactive mode for special files (shopping list, tasks, calendar, recipes, mealplan)
        this.switchEditorTab('special');
        this.renderSpecialView(data.type, path, data.content);
      } else {
        tabSpecial.style.display = 'none';
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

    [tabSpecial, tabWysiwyg, tabRaw].forEach(t => t.classList.remove('active'));
    [paneSpecial, paneWysiwyg, paneRaw].forEach(p => p.style.display = 'none');

    if (tabName === 'special') {
      tabSpecial.classList.add('active');
      paneSpecial.style.display = 'block';
    } else if (tabName === 'raw') {
      tabRaw.classList.add('active');
      paneRaw.style.display = 'block';
      const rawTextarea = document.getElementById('raw-editor-text');
      if (rawTextarea) rawTextarea.value = this.state.currentFileContent;
    } else {
      tabWysiwyg.classList.add('active');
      paneWysiwyg.style.display = 'block';
      this.renderWYSIWYG(this.state.currentFileContent);
    }
  },

  renderWYSIWYG(markdownText) {
    const pane = document.getElementById('pane-wysiwyg');
    if (!pane) return;
    pane.innerHTML = this.parseMarkdownToHTML(markdownText);
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
    ['shopping', 'recipe', 'mealplan', 'todo', 'calendar'].forEach(k => {
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
