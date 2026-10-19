let CONFIG = { demo_user_name: 'Demo User' };
let lastListFilter = null;

async function fetchJSON(url) {
    const res = await fetch(url);
    return res.json();
}

function getInitials(name) {
    if (!name) return '??';
    return name.split(/\s+/).map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

function formatNumber(n) {
    return Number(n).toLocaleString();
}

function formatDatetime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Lightweight Markdown + autolink for journal comments (demo UI).
 * Escape-first so raw HTML in bodies cannot execute; then apply a small
 * subset: headings, lists, hr, **bold**, *italic*, `code`, [text](url),
 * and bare http(s) URLs.
 */
function formatCommentHtml(raw) {
    if (!raw) return '';
    const lines = String(raw).replace(/\r\n/g, '\n').split('\n');
    const blocks = [];
    let i = 0;

    while (i < lines.length) {
        const line = lines[i];
        const trimmed = line.trim();

        if (!trimmed) {
            i += 1;
            continue;
        }

        if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
            blocks.push('<hr class="sn-md-hr">');
            i += 1;
            continue;
        }

        const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
        if (heading) {
            const level = heading[1].length;
            blocks.push(
                `<h${level} class="sn-md-h sn-md-h${level}">${formatInlineMd(heading[2])}</h${level}>`
            );
            i += 1;
            continue;
        }

        if (/^[-*]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) {
            const ordered = /^\d+\.\s+/.test(trimmed);
            const items = [];
            while (i < lines.length) {
                const t = lines[i].trim();
                if (!t) break;
                const m = ordered ? t.match(/^\d+\.\s+(.+)$/) : t.match(/^[-*]\s+(.+)$/);
                if (!m) break;
                items.push(`<li>${formatInlineMd(m[1])}</li>`);
                i += 1;
            }
            const tag = ordered ? 'ol' : 'ul';
            blocks.push(`<${tag} class="sn-md-list">${items.join('')}</${tag}>`);
            continue;
        }

        const para = [trimmed];
        i += 1;
        while (i < lines.length) {
            const t = lines[i].trim();
            if (!t) break;
            if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) break;
            if (/^#{1,3}\s+/.test(t)) break;
            if (/^[-*]\s+/.test(t) || /^\d+\.\s+/.test(t)) break;
            para.push(t);
            i += 1;
        }
        blocks.push(`<p class="sn-md-p">${formatInlineMd(para.join(' '))}</p>`);
    }

    return `<div class="sn-comment-body">${blocks.join('') || '<p class="sn-md-p"></p>'}</div>`;
}

function formatInlineMd(text) {
    // Escape first — all subsequent inserts are our own tags / sanitized hrefs.
    let s = escapeHtml(text);
    const slots = [];
    const stash = (html) => {
        const key = `\u0000MD${slots.length}\u0000`;
        slots.push(html);
        return key;
    };

    // [label](https://…) — href must be http(s) only
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_, label, href) => {
        const safeHref = sanitizeUrl(href);
        if (!safeHref) return label;
        return stash(
            `<a class="sn-md-link" href="${safeHref}" target="_blank" rel="noopener noreferrer">${label}</a>`
        );
    });

    // `code`
    s = s.replace(/`([^`]+)`/g, (_, code) => stash(`<code class="sn-md-code">${code}</code>`));

    // Bare URLs (not already stashed). Trailing punctuation peeled off.
    s = s.replace(/(https?:\/\/[^\s<]+)/g, (match) => {
        let url = match;
        let trail = '';
        while (/[.,;:!?)\]}'"]$/.test(url)) {
            trail = url.slice(-1) + trail;
            url = url.slice(0, -1);
        }
        const safeHref = sanitizeUrl(url);
        if (!safeHref) return match;
        return stash(
            `<a class="sn-md-link" href="${safeHref}" target="_blank" rel="noopener noreferrer">${url}</a>`
        ) + trail;
    });

    // **bold** then *italic* (avoid matching across slots)
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');

    for (let n = 0; n < slots.length; n += 1) {
        s = s.split(`\u0000MD${n}\u0000`).join(slots[n]);
    }
    return s;
}

function sanitizeUrl(href) {
    if (!href) return '';
    // After escapeHtml, & → &amp; — decode for validation only
    const decoded = String(href)
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"');
    if (!/^https?:\/\//i.test(decoded)) return '';
    // Re-escape attribute-sensitive chars for href
    return decoded
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// ===== ROUTING =====
function showView(viewId) {
    document.querySelectorAll('.sn-view').forEach(v => v.style.display = 'none');
    const el = document.getElementById(viewId);
    if (el) el.style.display = '';
}

function navigate(hash) {
    window.location.hash = hash;
}

async function handleRoute() {
    const hash = window.location.hash || '#overview';
    const pill = document.getElementById('headerPill');

    if (hash === '#overview' || hash === '' || hash === '#') {
        showView('view-overview');
        pill.textContent = 'Incident Overview ☆';
        await loadOverview();
    } else if (hash.startsWith('#incidents/')) {
        const num = hash.split('/')[1];
        showView('view-detail');
        pill.textContent = 'Incident - ' + CONFIG.demo_user_name + ' ☆';
        await loadDetail(num);
    } else if (hash.startsWith('#incidents')) {
        showView('view-list');
        pill.textContent = 'Incidents View: Self Service ☆';
        const params = new URLSearchParams(hash.includes('?') ? hash.split('?')[1] : '');
        await loadList(params);
    } else {
        showView('view-overview');
        pill.textContent = 'Incident Overview ☆';
        await loadOverview();
    }
}

// ===== OVERVIEW =====
let openChart = null;
let olderChart = null;

async function loadOverview() {
    const data = await fetchJSON('/api/v1/incidents/stats');
    const s = data.result;

    const openedEl = document.getElementById('stat-opened-today');
    const val = s.incidents_opened_today;
    openedEl.textContent = formatNumber(val);
    openedEl.className = 'sn-hero-number' + (val > 0 ? ' sn-hero-accent' : '');

    document.getElementById('stat-unassigned').textContent = formatNumber(s.unassigned_incidents);

    const overdueEl = document.getElementById('stat-overdue');
    overdueEl.textContent = formatNumber(s.overdue_incidents);
    overdueEl.className = 'sn-hero-number' + (s.overdue_incidents === 0 ? ' sn-hero-zero' : '');

    document.getElementById('stat-open').textContent = formatNumber(s.open_incidents);
    document.getElementById('stat-not-updated').textContent = formatNumber(s.not_updated_7_days);
    document.getElementById('stat-older-30').textContent = formatNumber(s.open_older_30_days);

    // Charts
    renderOpenChart(s.open_by_assignment_group);
    renderOlderChart(s.older_30_by_priority);

    // Populate assignment group dropdown
    const groupSelect = document.querySelector('.sn-dashboard-sidebar .sn-sidebar-section:last-child select');
    if (groupSelect && groupSelect.options.length <= 1) {
        Object.keys(s.open_by_assignment_group).sort().forEach(g => {
            const opt = document.createElement('option');
            opt.textContent = g;
            groupSelect.appendChild(opt);
        });
    }
}

function renderOpenChart(data) {
    const ctx = document.getElementById('chart-open-grouped');
    if (!ctx) return;

    if (openChart) openChart.destroy();

    const sorted = Object.entries(data).sort((a, b) => b[1] - a[1]);
    const labels = sorted.map(e => e[0]);
    const values = sorted.map(e => e[1]);

    openChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Incident Count',
                data: values,
                backgroundColor: '#26c6da',
                borderColor: '#26c6da',
                borderWidth: 1,
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'Incident Count' }, ticks: { precision: 0 } },
                x: { ticks: { maxRotation: 45, minRotation: 20, font: { size: 11 } } }
            }
        }
    });
}

function renderOlderChart(data) {
    const ctx = document.getElementById('chart-older-grouped');
    if (!ctx) return;

    if (olderChart) olderChart.destroy();

    const sorted = Object.entries(data).sort((a, b) => {
        const numA = parseInt(a[0]) || 99;
        const numB = parseInt(b[0]) || 99;
        return numA - numB;
    });
    const labels = sorted.map(e => e[0]);
    const values = sorted.map(e => e[1]);

    olderChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Incident Count',
                data: values,
                backgroundColor: '#26c6da',
                borderColor: '#26c6da',
                borderWidth: 1,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { beginAtZero: true, ticks: { precision: 0 } },
                y: { ticks: { font: { size: 11 } } }
            }
        }
    });
}

// ===== LIST =====
async function loadList(params) {
    let url = '/api/v1/incidents?limit=100';
    let breadcrumb = 'All';

    const filter = params.get('filter');
    lastListFilter = filter;

    if (filter === 'opened_today') {
        url += '&opened_today=1';
        breadcrumb = 'All &gt; Incident state in New &gt; Opened on Today';
    } else if (filter === 'open') {
        url += '&open_only=1';
        breadcrumb = 'All &gt; Open Incidents';
    } else if (filter === 'unassigned') {
        url += '&open_only=1';
        breadcrumb = 'All &gt; Unassigned Incidents';
    } else if (filter === 'not_updated_7d') {
        url += '&not_updated_days=7';
        breadcrumb = 'All &gt; Not Updated for 7 Days';
    } else if (filter === 'older_30d') {
        url += '&older_than_days=30';
        breadcrumb = 'All &gt; Open Incidents older than 30 Days';
    } else if (filter === 'overdue') {
        url += '&open_only=1';
        breadcrumb = 'All &gt; Overdue Incidents';
    }

    document.getElementById('listBreadcrumb').innerHTML = breadcrumb;

    const data = await fetchJSON(url);
    const tbody = document.getElementById('incidentTableBody');
    tbody.innerHTML = '';

    let incidents = data.result;
    if (filter === 'unassigned') {
        incidents = incidents.filter(i => !i.assignment_group);
    }

    incidents.forEach(inc => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><input type="checkbox"></td>
            <td></td>
            <td><a class="sn-link" href="#incidents/${escapeHtml(inc.number)}">${escapeHtml(inc.number)}</a></td>
            <td>${formatDatetime(inc.opened_at)}</td>
            <td>${escapeHtml(inc.short_description)}</td>
            <td>${escapeHtml(inc.state)}</td>
            <td>${escapeHtml(inc.created_by)}</td>
            <td>${formatDatetime(inc.sys_created_on)}</td>
        `;
        tbody.appendChild(tr);
    });
}

// ===== DETAIL =====
async function loadDetail(number) {
    const data = await fetchJSON('/api/v1/incidents/' + encodeURIComponent(number));
    if (data.error) {
        document.getElementById('detailBody').innerHTML = '<p style="padding:20px;color:#c00;">Incident not found.</p>';
        return;
    }

    const inc = data.result;
    const userName = inc.caller_id || CONFIG.demo_user_name;
    const userInitials = getInitials(userName);

    document.getElementById('detailUser').textContent = userName;
    document.getElementById('headerPill').textContent = 'Incident - ' + userName + ' ☆';

    const body = document.getElementById('detailBody');
    body.innerHTML = `
        <div class="sn-form-grid">
            <!-- Left Column -->
            <div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Number</span>
                    <div class="sn-form-value">
                        <input type="text" class="sn-form-input sn-form-input-readonly" value="${escapeHtml(inc.number)}" readonly>
                    </div>
                </div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Caller</span>
                    <div class="sn-form-value" style="display:flex;align-items:center;gap:4px;">
                        <input type="text" class="sn-form-input" value="${escapeHtml(userName)}" readonly>
                        <button class="sn-form-search-btn">&#128269;</button>
                        <button class="sn-form-icon-btn" title="View">&#128100;</button>
                        <button class="sn-form-icon-btn" title="Info">&#9432;</button>
                    </div>
                </div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Watch list</span>
                    <div class="sn-form-value">
                        <div class="sn-watch-icons">
                            <span class="sn-watch-icon">&#128274;</span>
                            <span class="sn-watch-icon">&#128101;</span>
                        </div>
                    </div>
                </div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Channel</span>
                    <div class="sn-form-value">
                        <select class="sn-form-select" disabled>
                            <option ${inc.channel === 'Email' ? 'selected' : ''}>Email</option>
                            <option ${inc.channel === 'Phone' ? 'selected' : ''}>Phone</option>
                            <option ${inc.channel === 'Self-service' ? 'selected' : ''}>Self-service</option>
                            <option ${inc.channel === 'Monitoring' ? 'selected' : ''}>Monitoring</option>
                        </select>
                    </div>
                </div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Correlation ID</span>
                    <div class="sn-form-value">
                        <input type="text" class="sn-form-input" value="" readonly>
                    </div>
                </div>
            </div>
            <!-- Right Column -->
            <div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Opened</span>
                    <div class="sn-form-value">
                        <input type="text" class="sn-form-input sn-form-input-readonly" value="${formatDatetime(inc.opened_at)}" readonly>
                    </div>
                </div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Closed</span>
                    <div class="sn-form-value">
                        <input type="text" class="sn-form-input sn-form-input-readonly" value="${formatDatetime(inc.closed_at)}" readonly>
                    </div>
                </div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Impact</span>
                    <div class="sn-form-value">
                        <select class="sn-form-select" disabled>
                            <option ${inc.impact === '1 - High' ? 'selected' : ''}>1 - High</option>
                            <option ${inc.impact === '2 - Medium' ? 'selected' : ''}>2 - Medium</option>
                            <option ${inc.impact === '3 - Low' ? 'selected' : ''}>3 - Low</option>
                        </select>
                    </div>
                </div>
                <div class="sn-form-row">
                    <span class="sn-form-label">State</span>
                    <div class="sn-form-value">
                        <select class="sn-form-select" disabled>
                            <option ${inc.state === 'New' ? 'selected' : ''}>New</option>
                            <option ${inc.state === 'Active' ? 'selected' : ''}>Active</option>
                            <option ${inc.state === 'Awaiting Problem' ? 'selected' : ''}>Awaiting Problem</option>
                            <option ${inc.state === 'Awaiting User Info' ? 'selected' : ''}>Awaiting User Info</option>
                            <option ${inc.state === 'Awaiting Evidence' ? 'selected' : ''}>Awaiting Evidence</option>
                            <option ${inc.state === 'Resolved' ? 'selected' : ''}>Resolved</option>
                            <option ${inc.state === 'Closed' ? 'selected' : ''}>Closed</option>
                        </select>
                    </div>
                </div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Problem</span>
                    <div class="sn-form-value" style="display:flex;align-items:center;gap:4px;">
                        <input type="text" class="sn-form-input" value="" readonly>
                        <button class="sn-form-search-btn">&#128269;</button>
                    </div>
                </div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Escalation</span>
                    <div class="sn-form-value">
                        <select class="sn-form-select" disabled>
                            <option ${(inc.escalation||'').includes('None') ? 'selected' : ''}>-- None --</option>
                            <option ${(inc.escalation||'').includes('1') ? 'selected' : ''}>1 - Yes</option>
                        </select>
                    </div>
                </div>
                <div class="sn-form-row">
                    <span class="sn-form-label">Category</span>
                    <div class="sn-form-value">
                        <select class="sn-form-select" disabled>
                            <option>${escapeHtml(inc.category || '')}</option>
                        </select>
                    </div>
                </div>
            </div>
            <!-- Full-width rows -->
            <div class="sn-form-row-wide">
                <div class="sn-form-row">
                    <span class="sn-form-label">Short description</span>
                    <div class="sn-form-value" style="display:flex;align-items:center;gap:4px;">
                        <input type="text" class="sn-form-input" value="${escapeHtml(inc.short_description)}" readonly>
                        <button class="sn-form-icon-btn" title="AI">&#128161;</button>
                    </div>
                </div>
            </div>
            <div class="sn-form-row-wide">
                <div class="sn-form-row">
                    <span class="sn-form-label">Parent incident</span>
                    <div class="sn-form-value">
                        <input type="text" class="sn-form-input" value="${escapeHtml(inc.parent_incident || '')}" readonly placeholder="—">
                    </div>
                </div>
            </div>
            <div class="sn-form-row-wide">
                <div class="sn-form-row">
                    <span class="sn-form-label">Child incidents</span>
                    <div class="sn-form-value">
                        <input type="text" class="sn-form-input" value="${escapeHtml((inc.child_incidents || []).join(', '))}" readonly placeholder="—">
                    </div>
                </div>
            </div>
            <div class="sn-form-row-wide">
                <div class="sn-form-row">
                    <span class="sn-form-label">Description</span>
                    <div class="sn-form-value">
                        <textarea class="sn-form-textarea" readonly>${escapeHtml(inc.description)}</textarea>
                    </div>
                </div>
            </div>
        </div>

        <!-- Related Search Results -->
        <div class="sn-related-search">
            <a href="#">Related Search Results &nbsp;&#9654;</a>
        </div>

        <!-- Additional comments -->
        <div style="display:flex;align-items:flex-start;margin-top:16px;">
            <span class="sn-comments-label">Additional comments (Customer visible)</span>
            <div style="flex:1;">
                <textarea id="newCommentBody" class="sn-form-textarea" placeholder="Additional comments (Customer visible)"></textarea>
                <div style="text-align:right;margin-top:6px;">
                    <button id="postCommentBtn" class="sn-btn sn-btn-outline" data-incident="${escapeHtml(inc.number)}">Post</button>
                </div>
            </div>
        </div>

        <!-- Activity -->
        <div class="sn-activity-section">
            <div class="sn-activity-header">
                <div>
                    <span class="sn-activity-title">Activities: ${(inc.comments || []).length + 1}</span>
                    <span class="sn-activity-count">(Filtered)</span>
                </div>
                <button class="sn-activity-filter-btn" style="margin-left: auto;">&#128295;</button>
            </div>
            <div class="sn-activity-entry">
                <div class="sn-activity-avatar">${escapeHtml(getInitials(inc.opened_by || userName))}</div>
                <div class="sn-activity-content">
                    <div class="sn-activity-meta">
                        <span>
                            <span class="sn-activity-user">${escapeHtml(inc.opened_by || userName)}</span>
                        </span>
                        <span>
                            <span class="sn-activity-type">Field changes</span>
                            <span class="sn-activity-date"> &bull; ${formatDatetime(inc.opened_at)}</span>
                        </span>
                    </div>
                    <div class="sn-activity-fields">
                        <span class="sn-activity-field-label">Impact</span>
                        <span class="sn-activity-field-value">${escapeHtml(inc.impact || '3 - Low')}</span>
                        <span class="sn-activity-field-label">Incident state</span>
                        <span class="sn-activity-field-value">${escapeHtml(inc.state)}</span>
                        <span class="sn-activity-field-label">Opened by</span>
                        <span class="sn-activity-field-value">${escapeHtml(inc.opened_by || userName)}</span>
                        <span class="sn-activity-field-label">Priority</span>
                        <span class="sn-activity-field-value">${escapeHtml(inc.priority)}</span>
                    </div>
                </div>
            </div>
            ${(inc.comments || []).slice().reverse().map(c => `
            <div class="sn-activity-entry">
                <div class="sn-activity-avatar">${escapeHtml(getInitials(c.created_by || 'api'))}</div>
                <div class="sn-activity-content">
                    <div class="sn-activity-meta">
                        <span>
                            <span class="sn-activity-user">${escapeHtml(c.created_by || 'api_user')}</span>
                        </span>
                        <span>
                            <span class="sn-activity-type">${escapeHtml(c.type === 'work_notes' ? 'Work notes' : 'Additional comments')}</span>
                            <span class="sn-activity-date"> &bull; ${formatDatetime(c.created_on)}</span>
                        </span>
                    </div>
                    <div class="sn-activity-fields sn-activity-comment">${formatCommentHtml(c.body || '')}</div>
                </div>
            </div>`).join('')}
        </div>

        <!-- Task type -->
        <div class="sn-task-type-row">
            <span class="sn-form-label">Task type</span>
            <div class="sn-form-value">
                <select class="sn-form-select" disabled>
                    <option selected>Incident</option>
                </select>
            </div>
        </div>

        <!-- Work notes list -->
        <div class="sn-worknotes">
            <div class="sn-worknotes-title">Work notes list</div>
            ${(inc.comments || []).length === 0
                ? '<div style="padding:8px 0;color:#666;font-size:13px;">No comments yet.</div>'
                : (inc.comments || []).map(c => `
            <div class="sn-worknote-entry" style="padding:10px 0;border-bottom:1px solid #e5e5e5;">
                <div style="font-size:12px;color:#666;margin-bottom:4px;">
                    <strong>${escapeHtml(c.created_by || 'api_user')}</strong>
                    &bull; ${formatDatetime(c.created_on)}
                    &bull; ${escapeHtml(c.type === 'work_notes' ? 'Work notes' : 'Additional comments')}
                </div>
                <div class="sn-worknote-body">${formatCommentHtml(c.body || '')}</div>
            </div>`).join('')}
        </div>

        <!-- Bottom actions -->
        <div class="sn-bottom-actions">
            <button class="sn-btn sn-btn-outline">Update</button>
            <button class="sn-btn sn-btn-outline">Update with Lens</button>
            <button class="sn-btn sn-btn-outline">Resolve Incident</button>
            <button class="sn-btn sn-btn-danger sn-btn">Delete</button>
        </div>
    `;

    const postBtn = document.getElementById('postCommentBtn');
    if (postBtn) {
        postBtn.addEventListener('click', async () => {
            const number = postBtn.getAttribute('data-incident');
            const ta = document.getElementById('newCommentBody');
            const text = (ta && ta.value || '').trim();
            if (!text) return;
            postBtn.disabled = true;
            try {
                const res = await fetch('/api/v1/incidents/' + encodeURIComponent(number) + '/comments', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        body: text,
                        created_by: CONFIG.demo_user_name || 'Demo User',
                        type: 'additional_comments',
                    }),
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    alert(err.error || ('Failed to post comment (' + res.status + ')'));
                    return;
                }
                await loadDetail(number);
            } finally {
                postBtn.disabled = false;
            }
        });
    }
}

// ===== CLICK HANDLERS =====
function setupClickHandlers() {
    document.getElementById('card-opened-today').addEventListener('click', () => navigate('#incidents?filter=opened_today'));
    document.getElementById('card-open-incidents').addEventListener('click', () => navigate('#incidents?filter=open'));
    document.getElementById('card-not-updated-7d').addEventListener('click', () => navigate('#incidents?filter=not_updated_7d'));
    document.getElementById('card-older-30d').addEventListener('click', () => navigate('#incidents?filter=older_30d'));

    document.getElementById('backBtn').addEventListener('click', () => {
        if (lastListFilter) {
            navigate('#incidents?filter=' + lastListFilter);
        } else {
            navigate('#overview');
        }
    });
}

// ===== INIT =====
async function init() {
    const cfg = await fetchJSON('/api/v1/config');
    CONFIG = cfg;

    document.getElementById('userAvatar').textContent = getInitials(CONFIG.demo_user_name);

    setupClickHandlers();
    await handleRoute();
}

window.addEventListener('hashchange', handleRoute);
document.addEventListener('DOMContentLoaded', init);
