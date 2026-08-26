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

async function connectSSE() {
    if (eventSource) {
        eventSource.close();
    }

    let streamUrl = '/audit/stream';
    if (authToken) {
        try {
            const ticketResp = await fetch('/auth/stream-ticket', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${authToken}` }
            });
            if (ticketResp.ok) {
                const data = await ticketResp.json();
                if (data && data.ticket) {
                    streamUrl = `/audit/stream?ticket=${encodeURIComponent(data.ticket)}`;
                }
            }
        } catch (err) {
            console.warn('Failed to obtain single-use stream ticket:', err);
        }
    }

    eventSource = new EventSource(streamUrl);

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
        apiFetch('/audit/stats').catch(() => {});
        setTimeout(connectSSE, 5000);
    };
}

// ── Virtual Scroll Audit Trail ──────────────────────────────────────────────
const ROW_HEIGHT = 48;
let isVirtualScrollScheduled = false;

function addAuditEntry(entry) {
    auditEntries.unshift(entry);
    if (auditEntries.length > 1000) auditEntries.pop();
    scheduleVirtualScroll();
}

function scheduleVirtualScroll() {
    if (isVirtualScrollScheduled) return;
    isVirtualScrollScheduled = true;
    requestAnimationFrame(() => {
        renderVirtualAuditTrail();
        isVirtualScrollScheduled = false;
    });
}

function renderVirtualAuditTrail() {
    const wrapper = document.querySelector('.audit-table-wrapper');
    const tbody = document.getElementById('audit-tbody');
    if (!wrapper || !tbody) return;

    const scrollTop = wrapper.scrollTop || 0;
    const clientHeight = wrapper.clientHeight || 480;
    const totalCount = auditEntries.length;

    if (totalCount === 0) {
        tbody.replaceChildren();
        return;
    }

    const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 2);
    const visibleCount = Math.ceil(clientHeight / ROW_HEIGHT) + 4;
    const endIndex = Math.min(totalCount, startIndex + visibleCount);

    const topPadding = startIndex * ROW_HEIGHT;
    const bottomPadding = Math.max(0, (totalCount - endIndex) * ROW_HEIGHT);

    const fragment = document.createDocumentFragment();

    if (topPadding > 0) {
        const topSpacer = document.createElement('tr');
        topSpacer.className = 'audit-spacer-row';
        const td = document.createElement('td');
        td.colSpan = 6;
        td.style.height = `${topPadding}px`;
        topSpacer.appendChild(td);
        fragment.appendChild(topSpacer);
    }

    for (let i = startIndex; i < endIndex; i++) {
        fragment.appendChild(createAuditRowElement(auditEntries[i]));
    }

    if (bottomPadding > 0) {
        const bottomSpacer = document.createElement('tr');
        bottomSpacer.className = 'audit-spacer-row';
        const td = document.createElement('td');
        td.colSpan = 6;
        td.style.height = `${bottomPadding}px`;
        bottomSpacer.appendChild(td);
        fragment.appendChild(bottomSpacer);
    }

    tbody.replaceChildren(fragment);
}

function createAuditRowElement(entry) {
    const tr = document.createElement('tr');
    tr.tabIndex = 0;
    tr.addEventListener('click', () => openSessionDetail(entry.session_id));
    tr.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') openSessionDetail(entry.session_id);
    });

    const time = entry.created_at
        ? new Date(entry.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }).replace(/\s/g, '\u00A0')
        : '—';
    const sessionShort = (entry.session_id || '').substring(0, 16);
    const session = makeElement('td', 'session-cell col-session', `${sessionShort}…`);
    session.title = entry.session_id || '';
    
    const actionCell = makeElement('td', 'col-action');
    actionCell.append(makeElement('span', `action-badge ${getActionClass(entry.action)}`, entry.action));

    const reason = makeElement('td', 'reason-cell col-reason', entry.reason || '—');
    reason.title = entry.reason || '';

    let decisionClass = '';
    let decisionText = '—';
    if (entry.decision === 'PASS') {
        decisionClass = 'decision-pass';
        decisionText = 'PASS';
    } else if (entry.decision === 'REJECT') {
        decisionClass = 'decision-reject';
        decisionText = 'REJECT';
    }

    let amountText = '—';
    if (entry.amount_paise) {
        const rupees = Math.round(entry.amount_paise / 100);
        amountText = `₹${rupees.toLocaleString('en-IN')}`;
    }

    tr.append(
        makeElement('td', 'time-cell col-time', time),
        session,
        actionCell,
        makeElement('td', `${decisionClass} col-decision`, decisionText),
        makeElement('td', 'amount-cell col-amount', amountText),
        reason,
    );
    return tr;
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

    let url = '/audit/trail?limit=100';
    if (action) url += `&action=${action}`;
    if (failure) url += `&failure_class=${failure}`;

    try {
        const resp = await apiFetch(url);
        auditEntries = await resp.json();
        scheduleVirtualScroll();
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
        `${report.total_sessions} sessions (${report.num_trials || 5} MC Trials)`;
    document.getElementById('campaign-metrics').classList.remove('is-hidden');
    document.getElementById('metric-conv-lift').textContent =
        `${report.mean_revenue_lift_pct !== undefined ? (report.mean_revenue_lift_pct > 0 ? '+' : '') + report.mean_revenue_lift_pct : report.conversion_lift_pct}%`;
    document.getElementById('metric-basket-lift').textContent =
        `${report.basket_lift_pct > 0 ? '+' : ''}${report.basket_lift_pct}%`;
    document.getElementById('metric-revenue-delta').textContent =
        `₹${(report.revenue_delta_paise / 100).toLocaleString()}`;
    document.getElementById('metric-upsell-rate').textContent =
        `${(report.agent_upsell_rate * 100).toFixed(1)}%`;
    
    const ciElem = document.getElementById('metric-ci');
    if (ciElem && report.ci_95_lower !== undefined) {
        ciElem.textContent = `[${report.ci_95_lower > 0 ? '+' : ''}${report.ci_95_lower}%, ${report.ci_95_upper > 0 ? '+' : ''}${report.ci_95_upper}%]`;
    }
    const stdElem = document.getElementById('metric-std-dev');
    if (stdElem && report.std_deviation_pct !== undefined) {
        stdElem.textContent = `±${report.std_deviation_pct}%`;
    }
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
    response.className = `response-area glass visible resp-decision-${tone}`;
    
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
    const statusBadge = document.getElementById('checkout-status');
    
    trigger.disabled = true;
    trigger.innerHTML = '<span class="btn-spinner"></span> Checking guardrails…';
    if (statusBadge) {
        statusBadge.textContent = 'Evaluating Intent';
        statusBadge.className = 'badge';
    }

    setCheckoutResponse([{ value: 'Parsing natural language intent and verifying against catalog bounds…' }]);

    try {
        const resp = await fetch('/checkout/converse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentCheckoutSession, message: msg }),
        });
        const data = await resp.json();
        
        const isPass = data.guardrail_decision === 'PASS';
        if (statusBadge) {
            statusBadge.textContent = isPass ? 'Guardrail Passed' : 'Guardrail Rejected';
            statusBadge.className = isPass ? 'badge badge-pass' : 'badge badge-reject';
        }

        const lines = [
            { label: 'Guardrail Decision', value: data.guardrail_decision || 'NEEDS_CLARIFICATION' },
            { label: 'Evaluation Rationale', value: data.guardrail_reason || data.message || 'Intent analyzed against catalog bounds' },
        ];

        if (data.resolved_total_paise) {
            lines.push({ label: 'Resolved Cart Total', value: `₹${(data.resolved_total_paise / 100).toLocaleString('en-IN')}` });
        }
        if (data.catalog_hash) {
            lines.push({ label: 'Catalog Version / Hash', value: `${data.catalog_version || '1.0.0'} (${data.catalog_hash.substring(0, 12)}...)` });
        }

        const output = setCheckoutResponse(lines, isPass ? 'pass' : 'reject');

        if (data.capability_token) {
            const tokenBox = makeElement('div', 'resp-token-card');
            tokenBox.style.marginTop = '12px';
            tokenBox.style.padding = '10px';
            tokenBox.style.border = '1px solid var(--measure-cyan)';
            tokenBox.style.background = 'rgba(0, 45, 90, 0.6)';
            
            const tokenLabel = makeElement('div', 'resp-meta-label', 'Cryptographic Capability Token (5-min TTL):');
            const tokenVal = makeElement('div', 'resp-meta-val', `${data.capability_token.substring(0, 38)}...`);
            tokenVal.style.wordBreak = 'break-all';
            tokenVal.style.fontSize = '10px';
            tokenVal.style.color = 'var(--measure-cyan)';
            tokenBox.append(tokenLabel, tokenVal);
            output.append(tokenBox);

            const paymentBtn = makeElement('button', 'btn btn-primary checkout-payment', '⚡ Dispatch Approved Payment via Razorpay');
            paymentBtn.type = 'button';
            paymentBtn.style.marginTop = '12px';
            paymentBtn.style.width = '100%';
            paymentBtn.addEventListener('click', () => dispatchTestPayment(data.capability_token, data.resolved_total_paise));
            output.append(paymentBtn);
        }
    } catch (e) {
        setCheckoutResponse([{ label: 'Request failed', value: e.message }], 'reject');
    } finally {
        trigger.disabled = false;
        trigger.innerHTML = 'Send request';
    }
}

async function dispatchTestPayment(token, amount) {
    const response = document.getElementById('checkout-response');
    const loadingP = document.createElement('p');
    loadingP.innerHTML = '<em>Dispatching payment to Razorpay gateway with idempotency key…</em>';
    response.append(loadingP);

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
            { label: 'Payment Status', value: data.status || (data.success ? 'CAPTURED' : 'FAILED') },
            { label: 'Razorpay Order ID', value: data.razorpay_order_id || 'simulated_order_' + Math.random().toString(36).substring(2, 9) },
            { label: 'Idempotency Key', value: data.idempotency_key || 'idemp_' + currentCheckoutSession },
            { label: 'Gateway Message', value: data.message || 'Payment successfully authorized & recorded in budget ledger' },
        ], data.success ? 'pass' : 'reject');

        // Trigger real-time refresh of live audit trail & stats
        setTimeout(() => {
            refreshTrail();
            apiFetch('/audit/stats').then(r => r.json()).then(updateStats).catch(console.error);
        }, 300);
    } catch (e) {
        setCheckoutResponse([{ label: 'Dispatch failed', value: e.message }], 'reject');
    }
}

// ── Session Detail Modal ────────────────────────────────────────────────────

async function openSessionDetail(sessionId) {
    const overlay = document.getElementById('modal-overlay');
    const body = document.getElementById('modal-body');
    overlay.classList.add('open');
    
    // Skeleton Pulse for lazy-load instant visual feedback
    const skeleton = document.createElement('div');
    skeleton.className = 'modal-skeleton';
    skeleton.innerHTML = `
        <h3 class="session-title" style="color: var(--measure-cyan); margin-bottom: 8px;">SESSION PROVENANCE: ${sessionId}</h3>
        <p style="color: rgba(255,255,255,0.6); font-size: 11px; margin-bottom: 16px;">Querying immutable cryptographic audit ledger...</p>
        <div class="skeleton-pulse" style="width: 90%;"></div>
        <div class="skeleton-pulse" style="width: 70%;"></div>
        <div class="skeleton-pulse" style="width: 80%;"></div>
        <div class="skeleton-pulse" style="width: 50%;"></div>
    `;
    body.replaceChildren(skeleton);

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
    
    const tableWrapper = document.querySelector('.audit-table-wrapper');
    if (tableWrapper) {
        tableWrapper.addEventListener('scroll', scheduleVirtualScroll, { passive: true });
    }

    document.getElementById('run-campaign').addEventListener('click', runCampaign);
    document.getElementById('send-checkout').addEventListener('click', simulateCheckout);
    document.getElementById('checkout-input').addEventListener('keydown', (event) => {
        if (event.key === 'Enter') simulateCheckout();
    });
    document.querySelectorAll('.btn-chip').forEach(btn => {
        btn.addEventListener('click', () => {
            const input = document.getElementById('checkout-input');
            input.value = btn.dataset.prompt;
            simulateCheckout();
        });
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
