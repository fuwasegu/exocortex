/**
 * Exocortex Dashboard - Main Application
 */

// State
const state = {
    currentTab: 'overview',
    memories: [],
    pagination: { offset: 0, limit: 20, total: 0 },
    eventSource: null,
    graph: { nodes: [], edges: [] },
};

// DOM Elements
const elements = {
    navButtons: document.querySelectorAll('.nav-btn'),
    tabContents: document.querySelectorAll('.tab-content'),
    healthBadge: document.getElementById('health-badge'),
    healthScore: document.querySelector('.health-score'),
    memoriesList: document.getElementById('memories-list'),
    pagination: document.getElementById('pagination'),
    modal: document.getElementById('memory-modal'),
    modalClose: document.getElementById('modal-close'),
    memoryDetail: document.getElementById('memory-detail'),
    dreamLog: document.getElementById('dream-log'),
    streamStatus: document.getElementById('stream-status'),
    streamStatusText: document.getElementById('stream-status-text'),
    filterType: document.getElementById('filter-type'),
    filterContext: document.getElementById('filter-context'),
    searchInput: document.getElementById('memory-search'),
    graphNetwork: document.getElementById('graph-network'),
};

// Graph state
let networkInstance = null;
let physicsEnabled = true;

// Type icons
const TYPE_ICONS = {
    insight: '💡',
    success: '✅',
    failure: '❌',
    decision: '🎯',
    note: '📝',
};

// ============ API Functions ============

async function fetchStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        if (data.success) {
            updateStatsDisplay(data.stats);
            populateContextFilter(data.stats.contexts);
        }
    } catch (err) {
        console.error('Error fetching stats:', err);
    }
}

async function fetchHealth() {
    try {
        const res = await fetch('/api/health');
        const data = await res.json();
        if (data.success) {
            updateHealthDisplay(data.health);
        }
    } catch (err) {
        console.error('Error fetching health:', err);
    }
}

async function fetchMemories() {
    try {
        const typeFilter = elements.filterType.value;
        const contextFilter = elements.filterContext.value;
        
        let url = `/api/memories?limit=${state.pagination.limit}&offset=${state.pagination.offset}`;
        if (typeFilter) url += `&type=${typeFilter}`;
        if (contextFilter) url += `&context=${encodeURIComponent(contextFilter)}`;
        
        const res = await fetch(url);
        const data = await res.json();
        
        if (data.success) {
            state.memories = data.memories;
            state.pagination.total = data.total;
            renderMemories();
            renderPagination();
        }
    } catch (err) {
        console.error('Error fetching memories:', err);
        elements.memoriesList.innerHTML = '<p class="loading">Error loading memories</p>';
    }
}

async function fetchMemoryDetail(memoryId) {
    try {
        const res = await fetch(`/api/memories/${memoryId}`);
        const data = await res.json();
        
        if (data.success) {
            renderMemoryDetail(data.memory, data.links);
            elements.modal.classList.add('active');
        }
    } catch (err) {
        console.error('Error fetching memory detail:', err);
    }
}

async function fetchGraph() {
    try {
        const res = await fetch('/api/graph');
        const data = await res.json();
        
        if (data.success) {
            state.graph = data.graph;
            renderGraph();
        }
    } catch (err) {
        console.error('Error fetching graph:', err);
    }
}

// ============ Display Functions ============

function updateStatsDisplay(stats) {
    document.getElementById('stat-total').textContent = stats.total_memories;
    document.getElementById('stat-insights').textContent = stats.by_type.insight || 0;
    document.getElementById('stat-successes').textContent = stats.by_type.success || 0;
    document.getElementById('stat-failures').textContent = stats.by_type.failure || 0;
    document.getElementById('stat-decisions').textContent = stats.by_type.decision || 0;
    document.getElementById('stat-notes').textContent = stats.by_type.note || 0;
    
    // Render contexts
    const contextsCloud = document.getElementById('contexts-cloud');
    contextsCloud.innerHTML = stats.contexts.map(ctx => 
        `<span class="tag context" data-context="${ctx}">${ctx}</span>`
    ).join('');
    
    // Render tags
    const tagsCloud = document.getElementById('tags-cloud');
    tagsCloud.innerHTML = stats.tags.map(tag => 
        `<span class="tag" data-tag="${tag}">${tag}</span>`
    ).join('');
    
    // Footer stats
    document.getElementById('footer-stats').textContent = 
        `${stats.total_memories} memories • ${stats.contexts_count} contexts • ${stats.tags_count} tags`;
}

function updateHealthDisplay(health) {
    elements.healthScore.textContent = health.score.toFixed(0);
    
    // Update badge color based on score
    const badge = elements.healthBadge;
    if (health.score >= 80) {
        badge.style.borderColor = 'rgba(0, 255, 136, 0.3)';
        badge.style.background = 'rgba(0, 255, 136, 0.1)';
    } else if (health.score >= 50) {
        badge.style.borderColor = 'rgba(255, 149, 0, 0.3)';
        badge.style.background = 'rgba(255, 149, 0, 0.1)';
    } else {
        badge.style.borderColor = 'rgba(255, 71, 87, 0.3)';
        badge.style.background = 'rgba(255, 71, 87, 0.1)';
    }
    
    // Render health details
    const detailsEl = document.getElementById('health-details');
    let html = '';
    
    if (health.issues.length > 0) {
        html += health.issues.map(issue => 
            `<div class="issue">⚠️ ${issue}</div>`
        ).join('');
    }
    
    html += health.suggestions.map(suggestion => 
        `<div class="suggestion">💡 ${suggestion}</div>`
    ).join('');
    
    detailsEl.innerHTML = html;
}

function populateContextFilter(contexts) {
    const select = elements.filterContext;
    select.innerHTML = '<option value="">All Contexts</option>';
    contexts.forEach(ctx => {
        const option = document.createElement('option');
        option.value = ctx;
        option.textContent = ctx;
        select.appendChild(option);
    });
}

function renderMemories() {
    if (state.memories.length === 0) {
        elements.memoriesList.innerHTML = '<p class="loading">No memories found</p>';
        return;
    }
    
    elements.memoriesList.innerHTML = state.memories.map(memory => `
        <div class="memory-item" data-id="${memory.id}">
            <div class="memory-item-header">
                <span class="memory-type">${TYPE_ICONS[memory.memory_type] || '📝'}</span>
                <span class="memory-meta">${memory.context_name} • ${formatDate(memory.created_at)}</span>
            </div>
            <div class="memory-summary">${escapeHtml(memory.summary)}</div>
            <div class="memory-tags">
                ${memory.tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
            </div>
        </div>
    `).join('');
    
    // Add click handlers
    elements.memoriesList.querySelectorAll('.memory-item').forEach(item => {
        item.addEventListener('click', () => {
            fetchMemoryDetail(item.dataset.id);
        });
    });
}

function renderPagination() {
    const totalPages = Math.ceil(state.pagination.total / state.pagination.limit);
    const currentPage = Math.floor(state.pagination.offset / state.pagination.limit) + 1;
    
    if (totalPages <= 1) {
        elements.pagination.innerHTML = '';
        return;
    }
    
    let html = '';
    
    html += `<button ${currentPage === 1 ? 'disabled' : ''} data-page="${currentPage - 1}">← Prev</button>`;
    
    for (let i = 1; i <= Math.min(totalPages, 5); i++) {
        html += `<button class="${i === currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }
    
    if (totalPages > 5) {
        html += `<span style="padding: 0.5rem">...</span>`;
        html += `<button data-page="${totalPages}">${totalPages}</button>`;
    }
    
    html += `<button ${currentPage === totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">Next →</button>`;
    
    elements.pagination.innerHTML = html;
    
    // Add click handlers
    elements.pagination.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', () => {
            const page = parseInt(btn.dataset.page);
            if (page && page !== currentPage) {
                state.pagination.offset = (page - 1) * state.pagination.limit;
                fetchMemories();
            }
        });
    });
}

function renderMemoryDetail(memory, links) {
    elements.memoryDetail.innerHTML = `
        <div class="memory-detail-header">
            <span class="memory-type" style="font-size: 2rem">${TYPE_ICONS[memory.memory_type] || '📝'}</span>
            <h2>${memory.context_name}</h2>
        </div>
        <div class="memory-meta" style="margin: 1rem 0">
            Created: ${formatDate(memory.created_at)} • 
            Accessed: ${memory.access_count} times
        </div>
        <div class="memory-tags">
            ${memory.tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
        </div>
        <div class="memory-detail-content">${escapeHtml(memory.content)}</div>
        ${links.length > 0 ? `
            <div class="memory-detail-links">
                <h4>🔗 Linked Memories (${links.length})</h4>
                ${links.map(link => `
                    <div class="link-item">
                        <strong>${link.relation_type}</strong>: ${escapeHtml(link.target_summary || link.target_id)}
                        ${link.reason ? `<br><small>${link.reason}</small>` : ''}
                    </div>
                `).join('')}
            </div>
        ` : ''}
    `;
}

// ============ Dream Log SSE ============

function connectDreamLog() {
    if (state.eventSource) {
        state.eventSource.close();
    }
    
    state.eventSource = new EventSource('/api/logs/stream');
    
    state.eventSource.onopen = () => {
        elements.streamStatus.classList.add('connected');
        elements.streamStatusText.textContent = 'Connected';
    };
    
    state.eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === 'log') {
                appendLogEntry(data.content);
            }
            // Ignore heartbeats
        } catch (err) {
            console.error('Error parsing SSE message:', err);
        }
    };
    
    state.eventSource.onerror = () => {
        elements.streamStatus.classList.remove('connected');
        elements.streamStatusText.textContent = 'Disconnected';
        
        // Reconnect after 5 seconds
        setTimeout(connectDreamLog, 5000);
    };
}

function appendLogEntry(content) {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    
    // Determine log level from content
    if (content.includes('ERROR') || content.includes('error')) {
        entry.classList.add('log-error');
    } else if (content.includes('WARNING') || content.includes('warning')) {
        entry.classList.add('log-warning');
    } else if (content.includes('SUCCESS') || content.includes('✅') || content.includes('complete')) {
        entry.classList.add('log-success');
    } else {
        entry.classList.add('log-info');
    }
    
    entry.textContent = content;
    elements.dreamLog.appendChild(entry);
    
    // Auto-scroll to bottom
    elements.dreamLog.scrollTop = elements.dreamLog.scrollHeight;
    
    // Limit entries to 500
    while (elements.dreamLog.children.length > 500) {
        elements.dreamLog.removeChild(elements.dreamLog.firstChild);
    }
}

// ============ Graph Visualization ============

const TYPE_COLORS = {
    insight: '#00ffff',
    success: '#00ff88',
    failure: '#ff4757',
    decision: '#ff9500',
    note: '#8b949e',
};

function renderGraph() {
    const container = document.getElementById('graph-network');
    if (!container) {
        console.warn('Graph container not found');
        return;
    }
    
    const { nodes, edges } = state.graph;
    
    if (nodes.length === 0) {
        container.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #8b949e; font-size: 16px;">No graph data available</div>';
        return;
    }
    
    // Prepare vis.js data
    const visNodes = new vis.DataSet(nodes.map(node => {
        const color = TYPE_COLORS[node.type] || TYPE_COLORS.note;
        return {
            id: node.id,
            label: node.label.length > 25 ? node.label.substring(0, 25) + '...' : node.label,
            title: `<div style="padding: 8px; max-width: 300px;"><strong>${TYPE_ICONS[node.type] || '📝'} ${node.type}</strong><br/>${node.label}</div>`,
            color: {
                background: color,
                border: color,
                highlight: {
                    background: color,
                    border: '#ffffff',
                },
                hover: {
                    background: color,
                    border: '#ffffff',
                },
            },
            font: {
                color: '#e6edf3',
                size: 12,
                face: 'JetBrains Mono, monospace',
            },
            borderWidth: 2,
            shadow: {
                enabled: true,
                color: color,
                size: 15,
                x: 0,
                y: 0,
            },
            size: 18,
        };
    }));
    
    const visEdges = new vis.DataSet(edges.map((edge, idx) => ({
        id: idx,
        from: edge.source,
        to: edge.target,
        title: edge.relation_type || 'related',
        color: {
            color: 'rgba(0, 255, 255, 0.3)',
            highlight: 'rgba(0, 255, 255, 0.8)',
            hover: 'rgba(0, 255, 255, 0.6)',
        },
        width: 1.5,
        smooth: {
            enabled: true,
            type: 'continuous',
            roundness: 0.5,
        },
        arrows: {
            to: {
                enabled: edge.relation_type && edge.relation_type !== 'related',
                scaleFactor: 0.5,
            },
        },
    })));
    
    // Network options - synapse-like physics
    const options = {
        nodes: {
            shape: 'dot',
            scaling: {
                min: 10,
                max: 30,
            },
        },
        edges: {
            smooth: {
                enabled: true,
                type: 'continuous',
            },
        },
        physics: {
            enabled: physicsEnabled,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -50,
                centralGravity: 0.01,
                springLength: 150,
                springConstant: 0.08,
                damping: 0.4,
                avoidOverlap: 0.5,
            },
            stabilization: {
                enabled: true,
                iterations: 200,
                updateInterval: 25,
            },
        },
        interaction: {
            hover: true,
            tooltipDelay: 100,
            zoomView: true,
            dragView: true,
            dragNodes: true,
            navigationButtons: false,
            keyboard: {
                enabled: true,
                speed: { x: 10, y: 10, zoom: 0.02 },
                bindToWindow: false,
            },
            zoomSpeed: 1,
        },
        layout: {
            improvedLayout: true,
            randomSeed: 42,
        },
    };
    
    // Clear previous network
    if (networkInstance) {
        networkInstance.destroy();
        networkInstance = null;
    }
    
    // Create new network
    const data = { nodes: visNodes, edges: visEdges };
    networkInstance = new vis.Network(container, data, options);
    
    // Click handler - show memory detail
    networkInstance.on('click', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            fetchMemoryDetail(nodeId);
        }
    });
    
    // Double-click to focus
    networkInstance.on('doubleClick', function(params) {
        if (params.nodes.length > 0) {
            networkInstance.focus(params.nodes[0], {
                scale: 1.5,
                animation: {
                    duration: 500,
                    easingFunction: 'easeInOutQuad',
                },
            });
        }
    });
}

// Graph control functions
function setupGraphControls() {
    const zoomInBtn = document.getElementById('graph-zoom-in');
    const zoomOutBtn = document.getElementById('graph-zoom-out');
    const fitBtn = document.getElementById('graph-fit');
    const physicsBtn = document.getElementById('graph-physics');
    
    if (zoomInBtn) {
        zoomInBtn.addEventListener('click', () => {
            if (networkInstance) {
                const scale = networkInstance.getScale();
                networkInstance.moveTo({ scale: scale * 1.3, animation: { duration: 300 } });
            }
        });
    }
    
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', () => {
            if (networkInstance) {
                const scale = networkInstance.getScale();
                networkInstance.moveTo({ scale: scale / 1.3, animation: { duration: 300 } });
            }
        });
    }
    
    if (fitBtn) {
        fitBtn.addEventListener('click', () => {
            if (networkInstance) {
                networkInstance.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
            }
        });
    }
    
    if (physicsBtn) {
        physicsBtn.addEventListener('click', () => {
            physicsEnabled = !physicsEnabled;
            physicsBtn.classList.toggle('active', physicsEnabled);
            if (networkInstance) {
                networkInstance.setOptions({ physics: { enabled: physicsEnabled } });
            }
        });
        // Set initial state
        physicsBtn.classList.toggle('active', physicsEnabled);
    }
}

// ============ Utilities ============

function formatDate(dateStr) {
    if (!dateStr) return 'Unknown';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============ Event Handlers ============

function switchTab(tabId) {
    state.currentTab = tabId;
    
    // Update nav buttons
    elements.navButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
    });
    
    // Update tab content
    elements.tabContents.forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tabId}`);
    });
    
    // Load data for tab
    if (tabId === 'overview') {
        fetchStats();
        fetchHealth();
    } else if (tabId === 'memories') {
        fetchMemories();
    } else if (tabId === 'dream') {
        connectDreamLog();
    } else if (tabId === 'graph') {
        fetchGraph();
    }
}

// ============ Initialization ============

function init() {
    // Nav button handlers
    elements.navButtons.forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
    
    // Modal handlers
    elements.modalClose.addEventListener('click', () => {
        elements.modal.classList.remove('active');
    });
    
    elements.modal.addEventListener('click', (e) => {
        if (e.target === elements.modal) {
            elements.modal.classList.remove('active');
        }
    });
    
    // Filter handlers
    elements.filterType.addEventListener('change', () => {
        state.pagination.offset = 0;
        fetchMemories();
    });
    
    elements.filterContext.addEventListener('change', () => {
        state.pagination.offset = 0;
        fetchMemories();
    });
    
    // Context/tag click handlers (delegated)
    document.getElementById('contexts-cloud').addEventListener('click', (e) => {
        if (e.target.classList.contains('tag')) {
            elements.filterContext.value = e.target.dataset.context;
            switchTab('memories');
            fetchMemories();
        }
    });
    
    document.getElementById('tags-cloud').addEventListener('click', (e) => {
        if (e.target.classList.contains('tag')) {
            // Could implement tag filtering in the future
            switchTab('memories');
        }
    });
    
    // Window resize handler for graph
    window.addEventListener('resize', () => {
        if (state.currentTab === 'graph' && networkInstance) {
            networkInstance.fit({ animation: false });
        }
    });
    
    // Setup graph controls
    setupGraphControls();
    
    // Initial load
    fetchStats();
    fetchHealth();
}

// Start the app
document.addEventListener('DOMContentLoaded', init);

