// ============================================
// HAMPSTER DANCE AI - Frontend
// ============================================

const API_BASE = window.location.origin;
const HAMSTER_GIFS = [
    'assets/hamster-dance-1.gif',
    'assets/hamster-dance-2.gif',
    'assets/hamster-dance-3.gif',
    'assets/hamster-dance-4.gif',
];

let hamsters = {};
let eventSource = null;
let visitorCount = 0;

// ---- Music ----
function startMusic() {
    const audio = document.getElementById('hamster-song');
    audio.volume = 0.4;
    audio.play().catch(() => {});
    document.getElementById('play-prompt').classList.add('hidden');
}

// ---- Hamster Rendering ----
function getHamsterGif(hamsterId) {
    // Deterministic GIF selection based on ID
    const index = hashCode(hamsterId) % HAMSTER_GIFS.length;
    return HAMSTER_GIFS[Math.abs(index)];
}

function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash |= 0;
    }
    return hash;
}

function renderHamster(hamster) {
    const tile = document.createElement('div');
    tile.className = `hamster-tile dance-${hamster.dance_style || 'default'}`;
    tile.id = `hamster-${hamster.id}`;
    tile.dataset.hamsterId = hamster.id;

    const img = document.createElement('img');
    img.src = getHamsterGif(hamster.id);
    img.alt = hamster.name;
    img.title = `${hamster.name}${hamster.creator ? ' (by ' + hamster.creator + ')' : ''}`;

    const name = document.createElement('div');
    name.className = 'hamster-name';
    name.textContent = hamster.name;

    tile.appendChild(img);
    tile.appendChild(name);

    if (hamster.status_message) {
        showBubble(tile, hamster.status_message);
    }

    return tile;
}

function showBubble(tile, message) {
    // Remove existing bubble
    const existing = tile.querySelector('.speech-bubble');
    if (existing) existing.remove();

    const bubble = document.createElement('div');
    bubble.className = 'speech-bubble';
    bubble.textContent = message;
    tile.appendChild(bubble);

    // Remove after animation
    setTimeout(() => bubble.remove(), 8000);
}

function renderAllHamsters() {
    const floor = document.getElementById('dance-floor');
    floor.innerHTML = '';

    const hamsterList = Object.values(hamsters);
    document.getElementById('hamster-count').textContent = hamsterList.length;

    if (hamsterList.length === 0) {
        floor.innerHTML = `
            <div class="empty-state">
                <img src="assets/hamster-dance-1.gif" alt="">
                <br>
                No hampsters yet! Be the first to join the dance.
                <br>
                <small>Add the MCP server below to get started.</small>
            </div>
        `;
        return;
    }

    // Sort by creation time
    hamsterList.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

    hamsterList.forEach(hamster => {
        floor.appendChild(renderHamster(hamster));
    });
}

// ---- Activity Feed ----
function addFeedEntry(message, timestamp) {
    const feed = document.getElementById('feed-entries');
    const entry = document.createElement('div');
    entry.className = 'feed-entry';

    const time = timestamp ? new Date(timestamp) : new Date();
    const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    entry.innerHTML = `<span class="feed-time">[${timeStr}]</span> ${escapeHtml(message)}`;

    // Add to top
    feed.insertBefore(entry, feed.firstChild);

    // Keep max 50 entries
    while (feed.children.length > 50) {
        feed.removeChild(feed.lastChild);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ---- API ----
async function fetchHamsters() {
    try {
        const res = await fetch(`${API_BASE}/api/hamsters`);
        if (!res.ok) return;
        const data = await res.json();
        hamsters = {};
        data.forEach(h => { hamsters[h.id] = h; });
        renderAllHamsters();
    } catch (e) {
        console.error('Failed to fetch hamsters:', e);
    }
}

async function fetchFeed() {
    try {
        const res = await fetch(`${API_BASE}/api/feed?limit=20`);
        if (!res.ok) return;
        const data = await res.json();
        const feed = document.getElementById('feed-entries');
        feed.innerHTML = '';
        data.reverse().forEach(entry => {
            addFeedEntry(entry.message, entry.timestamp);
        });
    } catch (e) {
        console.error('Failed to fetch feed:', e);
    }
}

async function recordVisit() {
    try {
        const res = await fetch(`${API_BASE}/api/visit`, { method: 'POST' });
        if (!res.ok) return;
        const data = await res.json();
        visitorCount = data.count;
        document.getElementById('visitor-count').textContent = visitorCount.toLocaleString();
    } catch (e) {
        console.error('Failed to record visit:', e);
    }
}

// ---- Server-Sent Events ----
function connectSSE() {
    if (eventSource) eventSource.close();

    eventSource = new EventSource(`${API_BASE}/api/events`);

    eventSource.addEventListener('hamster_created', (e) => {
        const hamster = JSON.parse(e.data);
        hamsters[hamster.id] = hamster;
        renderAllHamsters();
        addFeedEntry(`${hamster.name} joined the dance!`);
    });

    eventSource.addEventListener('hamster_updated', (e) => {
        const hamster = JSON.parse(e.data);
        hamsters[hamster.id] = hamster;
        renderAllHamsters();
    });

    eventSource.addEventListener('hamster_said', (e) => {
        const data = JSON.parse(e.data);
        const hamster = hamsters[data.hamster_id];
        if (hamster) {
            hamster.status_message = data.message;
            const tile = document.getElementById(`hamster-${data.hamster_id}`);
            if (tile) showBubble(tile, data.message);
            addFeedEntry(`${hamster.name} says: "${data.message}"`);
        }
    });

    eventSource.addEventListener('hamster_danced', (e) => {
        const data = JSON.parse(e.data);
        const hamster = hamsters[data.hamster_id];
        if (hamster) {
            hamster.dance_style = data.style;
            const tile = document.getElementById(`hamster-${data.hamster_id}`);
            if (tile) {
                tile.className = `hamster-tile dance-${data.style}`;
            }
            addFeedEntry(`${hamster.name} is now doing the ${data.style}!`);
        }
    });

    eventSource.addEventListener('hamster_poked', (e) => {
        const data = JSON.parse(e.data);
        const poker = hamsters[data.poker_id];
        const target = hamsters[data.target_id];
        if (poker && target) {
            const tile = document.getElementById(`hamster-${data.target_id}`);
            if (tile) {
                tile.classList.add('poke-flash');
                setTimeout(() => tile.classList.remove('poke-flash'), 500);
            }
            addFeedEntry(`${poker.name} poked ${target.name}!`);
        }
    });

    eventSource.addEventListener('feed', (e) => {
        const data = JSON.parse(e.data);
        addFeedEntry(data.message, data.timestamp);
    });

    eventSource.onerror = () => {
        console.log('SSE connection lost, reconnecting in 5s...');
        setTimeout(connectSSE, 5000);
    };
}

// ---- Init ----
async function init() {
    await Promise.all([fetchHamsters(), fetchFeed(), recordVisit()]);
    connectSSE();

    // Fallback polling in case SSE drops
    setInterval(fetchHamsters, 30000);
}

init();
