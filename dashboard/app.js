/**
 * Agentic Commerce — Audit Dashboard JavaScript
 * SSE listener, Chart.js charts, real-time ledger view, session deep-dive.
 */

// ── State ───────────────────────────────────────────────────────────────────

let auditEntries = [];
let eventSource = null;
let campaignChart = null;
let failureChart = null;
let lastStats = null;
let authToken = localStorage.getItem('agentic_auth_token') || '';

async function apiFetch(url, options = {}) {
    options.headers = { 
        'Authorization': `Bearer ${authToken}`,
        ...(options.headers || {})
    };
    const res = await fetch(url, options);
    if (res.status === 401) {
        document.getElementById('login-modal').classList.add('open');
        throw new Error('Unauthorized');
    }
    return res;
}

function setText(element, value) {
    element.textContent = value == null || value === '' ? '—' : String(value);
}

function makeElement(tag, className, value) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (value !== undefined) setText(element, value);
    return element;
}

function setConnectionStatus(label, state) {
    const status = document.getElementById('sse-status');
    status.replaceChildren(makeElement('span', `dot dot-${state}`), makeElement('span', '', label));
}

// ── SSE Connection ──────────────────────────────────────────────────────────

function connectSSE() {
    if (eventSource) {
        eventSource.close();
    }
    const qs = authToken ? `?token=${encodeURIComponent(authToken)}` : '';
    eventSource = new EventSource(`/audit/stream${qs}`);

    eventSource.onopen = () => {
        setConnectionStatus('Live', 'live');
    };

    eventSource.onmessage = (event) => {
        try {
            const entry = JSON.parse(event.data);
            addAuditEntry(entry);
        } catch (e) {
            console.warn('Failed to parse SSE message:', e);
        }
    };

    eventSource.addEventListener('stats', (event) => {
        try {
            const stats = JSON.parse(event.data);
            updateStats(stats);
            lastStats = stats;
        } catch (e) {
            console.warn('Failed to parse stats:', e);
        }
    });

    eventSource.onerror = (e) => {
        setConnectionStatus('Reconnecting', 'error');
        // If auth fails, we likely get disconnected or 401. Re-check stats to trigger login if needed.
        apiFetch('/audit/stats').catch(() => {});
        setTimeout(connectSSE, 5000);
    };
}

// ── Audit Trail ─────────────────────────────────────────────────────────────

function addAuditEntry(entry) {
    auditEntries.unshift(entry);
    if (auditEntries.length > 200) auditEntries.pop();
    renderAuditRow(entry, true);
}

function renderAuditRow(entry, isNew = false) {
    const tbody = document.getElementById('audit-tbody');
    const tr = document.createElement('tr');
    if (isNew) tr.classList.add('new-row');

    tr.tabIndex = 0;
    tr.addEventListener('click', () => openSessionDetail(entry.session_id));
    tr.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') openSessionDetail(entry.session_id);
    });

    // Time: format as "H:MM:SS AM" with non-breaking spaces to prevent wrapping
    const time = entry.created_at
        ? new Date(entry.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }).replace(/\s/g, '\u00A0')
        : '—';
    const sessionShort = (entry.session_id || '').substring(0, 16);
    const session = makeElement('td', 'session-cell', `${sessionShort}…`);
    session.title = entry.session_id || '';
    const actionCell = document.createElement('td');
    actionCell.append(makeElement('span', `action-badge ${getActionClass(entry.action)}`, entry.action));

    // Reason: full text in title for tooltip
    const reason = makeElement('td', 'reason-cell', entry.reason || '—');
    reason.title = entry.reason || '';

    // Decision: handle null/empty gracefully
    let decisionClass = '';
    let decisionText = '—';
    if (entry.decision === 'PASS') {
        decisionClass = 'decision-pass';
        decisionText = 'PASS';
    } else if (entry.decision === 'REJECT') {
        decisionClass = 'decision-reject';
        decisionText = 'REJECT';
    }

    // Amount: consistent formatting - ₹X,XXX (no decimals)
    let amountText = '—';
    if (entry.amount_paise) {
        const rupees = Math.round(entry.amount_paise / 100);
        amountText = `₹${rupees.toLocaleString('en-IN')}`;
    }

    tr.append(
        makeElement('td', 'time-cell', time),
        session,
        actionCell,
        makeElement('td', decisionClass, decisionText),
        makeElement('td', 'amount-cell', amountText),
        reason,
    );
    tbody.insertBefore(tr, tbody.firstChild);
    while (tbody.children.length > 100) tbody.removeChild(tbody.lastChild);
}

function getActionClass(action) {
    const map = {
        'GUARDRAIL_CHECK': 'action-guardrail',
        'PAYMENT_DISPATCH': 'action-payment',
        'WEBHOOK_RECEIVED': 'action-webhook',
        'UPSELL_OFFER': 'action-upsell',
        'RECONCILIATION': 'action-reconciliation',
        'DEAD_LETTER': 'action-dead-letter',
    };
    return map[action] || '';
}

async function refreshTrail() {
    const action = document.getElementById('filter-action').value;
    const failure = document.getElementById('filter-failure').value;

    let url = '/audit/trail?limit=50';
    if (action) url += `&action=${action}`;
    if (failure) url += `&failure_class=${failure}`;

    try {
        const resp = await apiFetch(url);
        const entries = await resp.json();
        const tbody = document.getElementById('audit-tbody');
        tbody.replaceChildren();
        entries.forEach(e => renderAuditRow(e, false));
    } catch (e) {
        console.error('Failed to refresh trail:', e);
    }
}

// ── Stats ───────────────────────────────────────────────────────────────────

function animateValue(id, start, end, duration, formatFn = (x) => x) {
    if (start === end) return;
    const obj = document.getElementById(id);
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        // easeOutQuart
        const ease = 1 - Math.pow(1 - progress, 4);
        const current = Math.floor(progress * (end - start) + start);
        obj.textContent = formatFn(current);
        if (progress < 1) {
            window.requestAnimationFrame(step);
        } else {
            obj.textContent = formatFn(end);
        }
    };
    window.requestAnimationFrame(step);
}

function updateStats(stats) {
    const formatInt = x => x;
    const formatMoney = x => {
        const rupees = Math.round(x / 100);
        return `₹${rupees.toLocaleString('en-IN')}`;
    };
    
    const currTotal = parseInt(document.getElementById('stat-total').textContent.replace(/,/g, '')) || 0;
    const passes = (stats.by_decision && stats.by_decision['PASS']) || 0;
    const currPasses = parseInt(document.getElementById('stat-passes').textContent.replace(/,/g, '')) || 0;
    const rejects = (stats.by_decision && stats.by_decision['REJECT']) || 0;
    const currRejects = parseInt(document.getElementById('stat-rejects').textContent.replace(/,/g, '')) || 0;
    
    animateValue('stat-total', currTotal, stats.total_entries || 0, 800, formatInt);
    animateValue('stat-passes', currPasses, passes, 800, formatInt);
    animateValue('stat-rejects', currRejects, rejects, 800, formatInt);

    const bs = stats.budget_summary || {};
    const currSessions = parseInt(document.getElementById('stat-sessions').textContent.replace(/,/g, '')) || 0;
    const currSpent = parseInt(document.getElementById('stat-spent').textContent.replace(/[^0-9]/g, '')) * 100 || 0; 
    // Wait, the spent might not match exactly due to locale, but this is a close approximation for demo
    
    animateValue('stat-sessions', currSessions, bs.total_sessions || 0, 800, formatInt);
    animateValue('stat-spent', currSpent, bs.total_spent_paise || 0, 800, formatMoney);
    
    const currDl = parseInt(document.getElementById('stat-deadletters').textContent.replace(/,/g, '')) || 0;
    animateValue('stat-deadletters', currDl, stats.unresolved_dead_letters || 0, 800, formatInt);

    updateFailureChart(stats.by_failure_class || {});
}

// ── Charts ──────────────────────────────────────────────────────────────────

function initCharts() {
    Chart.defaults.color = 'rgba(255, 255, 255, 0.8)';
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.12)';
    Chart.defaults.font.family = "'Roboto Mono', monospace";

    // Campaign chart
    const campCtx = document.getElementById('campaign-chart').getContext('2d');
    campaignChart = new Chart(campCtx, {
        type: 'bar',
        data: {
            labels: ['Conversion Rate', 'Avg Basket (₹)', 'Total Revenue (₹)'],
            datasets: [
                {
                    label: 'Baseline',
                    data: [0, 0, 0],
                    backgroundColor: 'rgba(255, 255, 255, 0.15)',
                    borderColor: 'rgba(255, 255, 255, 0.6)',
                    borderWidth: 1,
                    borderRadius: 0,
                },
                {
                    label: 'With Agent',
                    data: [0, 0, 0],
                    backgroundColor: 'rgba(0, 255, 255, 0.25)',
                    borderColor: '#00FFFF',
                    borderWidth: 1,
                    borderRadius: 0,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top', labels: { color: 'rgba(255, 255, 255, 0.8)' } }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255, 255, 255, 0.1)' }
                },
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.1)' }
                }
            },
        },
    });

    // Failure chart
    const failCtx = document.getElementById('failure-chart').getContext('2d');
    failureChart = new Chart(failCtx, {
        type: 'doughnut',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: [
                    '#FF3333',
                    '#00FFFF',
                    'rgba(255, 255, 255, 0.8)',
                    '#facc15',
                    '#a855f7',
                ],
                borderWidth: 2,
                borderColor: '#003366',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 10, padding: 12, color: 'rgba(255, 255, 255, 0.8)' } },
            },
        },
    });
}

function updateCampaignChart(report) {
    campaignChart.data.datasets[0].data = [
        (report.baseline_conversion_rate * 100).toFixed(1),
        report.baseline_avg_basket_paise / 100,
        report.baseline_total_revenue_paise / 100,
    ];
    campaignChart.data.datasets[1].data = [
        (report.agent_conversion_rate * 100).toFixed(1),
        report.agent_avg_basket_paise / 100,
        report.agent_total_revenue_paise / 100,
    ];
    campaignChart.update();

    document.getElementById('campaign-badge').textContent =
        `${report.total_sessions} sessions`;
    document.getElementById('campaign-metrics').classList.remove('is-hidden');
    document.getElementById('metric-conv-lift').textContent =
        `${report.conversion_lift_pct > 0 ? '+' : ''}${report.conversion_lift_pct}%`;
    document.getElementById('metric-basket-lift').textContent =
        `${report.basket_lift_pct > 0 ? '+' : ''}${report.basket_lift_pct}%`;
    document.getElementById('metric-revenue-delta').textContent =
        `₹${(report.revenue_delta_paise / 100).toLocaleString()}`;
    document.getElementById('metric-upsell-rate').textContent =
        `${(report.agent_upsell_rate * 100).toFixed(1)}%`;
}

function updateFailureChart(failures) {
    const labels = Object.keys(failures);
    const data = Object.values(failures);

    failureChart.data.labels = labels;
    failureChart.data.datasets[0].data = data;
    failureChart.update();
}

// ── Campaign ────────────────────────────────────────────────────────────────

async function runCampaign() {
    const btn = document.getElementById('run-campaign');
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-spinner"></span> Running campaign…';

    try {
        const resp = await apiFetch('/campaign/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ total_sessions: 50, enable_upsell: true }),
        });
        const report = await resp.json();
        updateCampaignChart(report);

        // Refresh stats
        const statsResp = await apiFetch('/audit/stats');
        const stats = await statsResp.json();
        updateStats(stats);

        // Refresh trail
        refreshTrail();
    } catch (e) {
        console.error('Campaign failed:', e);
        alert('Campaign run failed. Check console for details.');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Run campaign';
    }
}

// ── Checkout Simulator ────────────────────────────────────────────────────────
let currentCheckoutSession = null;

function setCheckoutResponse(lines, tone = 'muted') {
    const response = document.getElementById('checkout-response');
    response.replaceChildren();
    const output = makeElement('div', `checkout-output checkout-${tone}`);
    for (const { label, value } of lines) {
        const line = document.createElement('p');
        if (label) line.append(makeElement('strong', '', `${label}: `));
        line.append(document.createTextNode(value));
        output.append(line);
    }
    response.append(output);
    return response;
}

async function simulateCheckout() {
    const input = document.getElementById('checkout-input');
    const msg = input.value.trim();
    if (!msg) return;

    if (!currentCheckoutSession) {
        currentCheckoutSession = 'demo-' + Math.random().toString(36).substring(2, 10);
    }

    const trigger = document.getElementById('send-checkout');
    
    trigger.disabled = true;
    trigger.innerHTML = '<span class="btn-spinner"></span> Checking guardrails…';

    setCheckoutResponse([{ value: 'Sending request to the guardrail…' }]);

    try {
        const resp = await fetch('/checkout/converse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentCheckoutSession, message: msg }),
        });
        const data = await resp.json();
        
        const output = setCheckoutResponse([
            { label: 'Decision', value: data.guardrail_decision || 'Needs clarification' },
            { label: 'Reason', value: data.guardrail_reason || data.message || 'No reason provided' },
        ], data.guardrail_decision === 'PASS' ? 'pass' : 'reject');
        if (data.capability_token) {
            const payment = makeElement('button', 'btn btn-primary checkout-payment', 'Dispatch approved payment');
            payment.type = 'button';
            payment.addEventListener('click', () => dispatchTestPayment(data.capability_token, data.resolved_total_paise));
            output.append(payment);
        }
        input.value = '';
    } catch (e) {
        setCheckoutResponse([{ label: 'Request failed', value: e.message }], 'reject');
    } finally {
        trigger.disabled = false;
        trigger.innerHTML = 'Send request';
    }
}

async function dispatchTestPayment(token, amount) {
    try {
        const resp = await fetch('/payment/dispatch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentCheckoutSession,
                capability_token: token,
                amount_paise: amount
            }),
        });
        const data = await resp.json();
        setCheckoutResponse([
            { label: 'Dispatch status', value: data.status },
            { label: 'Message', value: data.message },
        ], data.success ? 'pass' : 'reject');
    } catch (e) {
        setCheckoutResponse([{ label: 'Dispatch failed', value: e.message }], 'reject');
    }
}

// ── Session Detail Modal ────────────────────────────────────────────────────

async function openSessionDetail(sessionId) {
    const overlay = document.getElementById('modal-overlay');
    const body = document.getElementById('modal-body');
    overlay.classList.add('open');
    body.replaceChildren(makeElement('p', 'modal-message', 'Loading session detail…'));

    try {
        const resp = await apiFetch(`/audit/session/${sessionId}`);
        const detail = await resp.json();
        renderSessionDetail(detail);
    } catch (e) {
        body.replaceChildren(makeElement('p', 'modal-message is-error', `Failed to load: ${e.message}`));
    }
}

function renderSessionDetail(detail) {
    const body = document.getElementById('modal-body');
    const nodes = [makeElement('h3', 'session-title', detail.session_id)];
    if (detail.budget) {
        const budget = detail.budget;
        nodes.push(makeElement(
            'p',
            'budget-summary',
            `Budget ₹${(budget.budget_paise / 100).toLocaleString()} · Spent ₹${(budget.spent_paise / 100).toLocaleString()} · Remaining ₹${((budget.budget_paise - budget.spent_paise) / 100).toLocaleString()} · ${budget.frozen ? 'Frozen' : 'Active'}`,
        ));
    }
    nodes.push(makeElement('h4', 'timeline-heading', 'Event timeline'));
    for (const entry of detail.audit_trail || []) {
        const item = document.createElement('article');
        item.className = 'timeline-item';
        item.append(
            makeElement('div', 'tl-time', entry.created_at ? new Date(entry.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : ''),
            makeElement('div', `tl-action ${entry.decision === 'PASS' ? 'decision-pass' : (entry.decision === 'REJECT' ? 'decision-reject' : '')}`, `${entry.action || 'Event'} — ${entry.decision || '—'}`),
            makeElement('div', 'tl-detail', entry.reason),
        );
        if (entry.amount_paise) {
            const rupees = Math.round(entry.amount_paise / 100);
            item.append(makeElement('div', 'tl-detail', `Amount: ₹${rupees.toLocaleString('en-IN')}`));
        }
        nodes.push(item);
    }
    body.replaceChildren(...nodes);
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('open');
}

// ── Init ────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new URLSearchParams();
        fd.append('username', document.getElementById('login-username').value);
        fd.append('password', document.getElementById('login-password').value);
        
        try {
            const res = await fetch('/auth/token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: fd
            });
            if (!res.ok) throw new Error('Login failed');
            const data = await res.json();
            authToken = data.access_token;
            localStorage.setItem('agentic_auth_token', authToken);
            document.getElementById('login-modal').classList.remove('open');
            document.getElementById('login-error').style.display = 'none';
            // Reload data
            initData();
        } catch(err) {
            document.getElementById('login-error').style.display = 'block';
        }
    });

    initCharts();
    initData();
    connectSSE();
    refreshTrail();
    initBlueprintCoordinates();
    document.getElementById('run-campaign').addEventListener('click', runCampaign);
    document.getElementById('send-checkout').addEventListener('click', simulateCheckout);
    document.getElementById('checkout-input').addEventListener('keydown', (event) => {
        if (event.key === 'Enter') simulateCheckout();
    });
    document.getElementById('filter-action').addEventListener('change', refreshTrail);
    document.getElementById('filter-failure').addEventListener('change', refreshTrail);
    document.getElementById('close-modal').addEventListener('click', closeModal);
    document.getElementById('modal-overlay').addEventListener('click', (event) => {
        if (event.target.id === 'modal-overlay') closeModal();
    });
});

function initBlueprintCoordinates() {
    const coordsElem = document.getElementById('cursor-coords');
    if (!coordsElem) return;
    window.addEventListener('mousemove', (e) => {
        const x = String(e.clientX).padStart(4, '0');
        const y = String(e.clientY).padStart(4, '0');
        coordsElem.textContent = `COORD: X[${x}] Y[${y}] | 1:1`;
    }, { passive: true });
}

function removeSplineWatermark() {
    const clean = () => {
        const viewer = document.getElementById('spline-bg');
        if (viewer && viewer.shadowRoot) {
            const logo = viewer.shadowRoot.querySelector('#logo') ||
                         viewer.shadowRoot.querySelector('a') ||
                         viewer.shadowRoot.querySelector('.spline-watermark');
            if (logo) {
                logo.style.display = 'none';
                logo.style.opacity = '0';
                logo.style.pointerEvents = 'none';
                logo.remove();
            }
        }
    };
    clean();
    const interval = setInterval(clean, 200);
    setTimeout(() => clearInterval(interval), 6000);
}

function initData() {
    connectSSE();
    refreshTrail();
    // Initial stats fetch
    apiFetch('/audit/stats')
        .then(r => r.json())
        .then(updateStats)
        .catch(console.error);
}

// Close modal on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});
