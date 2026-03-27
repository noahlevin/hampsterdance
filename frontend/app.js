// ============================================
// HAMPSTER DANCE AI - Frontend
// ============================================

const API_BASE = window.location.origin;
const HAMSTER_GIFS = [
    'assets/hamster-dance-1.gif',
    'assets/hamster-dance-2.gif',
    'assets/hamster-dance-3.gif',
    'assets/hamster-dance-4.gif',
    'assets/hamster-dance-5.gif',
    'assets/hamster-dance-6.gif',
    'assets/hamster-dance-7.gif',
    'assets/hamster-dance-8.gif',
];

let hamsters = {};
let eventSource = null;
let visitorCount = 0;
let totalHamsterCount = 0;
let currentBrowsePage = 1;
const DANCE_FLOOR_MAX = 50;

// ---- Music ----
function startMusic() {
    const audio = document.getElementById('hamster-song');
    const isMuted = localStorage.getItem('hampster-muted') === 'true';
    audio.volume = 0.4;
    audio.muted = isMuted;
    audio.play().catch(() => {});
    document.getElementById('play-prompt').classList.add('hidden');
    updateMuteButton();
}

function toggleMute() {
    const audio = document.getElementById('hamster-song');
    audio.muted = !audio.muted;
    localStorage.setItem('hampster-muted', audio.muted ? 'true' : 'false');
    updateMuteButton();
}

function updateMuteButton() {
    const audio = document.getElementById('hamster-song');
    const btn = document.getElementById('mute-btn');
    if (audio.muted) {
        btn.textContent = 'SOUND: OFF';
        btn.classList.add('muted');
    } else {
        btn.textContent = 'SOUND: ON';
        btn.classList.remove('muted');
    }
}

// ---- Hamster Rendering ----
function getHamsterGif(hamster) {
    // Use base_gif trait from database if available, fallback to hash
    if (hamster && typeof hamster === 'object' && hamster.base_gif) {
        const gifNum = Math.min(Math.max(hamster.base_gif, 1), HAMSTER_GIFS.length);
        return HAMSTER_GIFS[gifNum - 1];
    }
    // Fallback for string IDs (search results, etc.)
    const id = (typeof hamster === 'string') ? hamster : hamster.id;
    const index = hashCode(id) % HAMSTER_GIFS.length;
    return HAMSTER_GIFS[Math.abs(index)];
}

function getAccessoryEmoji(accessory) {
    const map = {
        'hat': '\u{1F3A9}', 'sunglasses': '\u{1F576}\uFE0F', 'crown': '\u{1F451}',
        'bowtie': '\u{1F380}', 'cape': '\u{1F9E3}', 'party-hat': '\u{1F973}',
        'headband': '\u{1F338}', 'monocle': '\u{1F9D0}'
    };
    return map[accessory] || '';
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
    img.src = getHamsterGif(hamster);
    img.alt = hamster.name;
    img.title = `${hamster.name}${hamster.creator ? ' (by ' + hamster.creator + ')' : ''}`;

    const name = document.createElement('div');
    name.className = 'hamster-name';
    name.textContent = hamster.name;

    tile.appendChild(img);
    tile.appendChild(name);

    // ---- Apply Boring Apes traits ----

    // Body hue (CSS hue-rotate filter)
    const filters = [];
    if (hamster.body_hue != null && hamster.body_hue !== 0) {
        filters.push(`hue-rotate(${hamster.body_hue}deg)`);
    }

    // Glow effect (drop-shadow using hamster's hue color)
    if (hamster.has_glow) {
        tile.classList.add('hamster-glow');
        const hue = hamster.body_hue || 0;
        filters.push(`drop-shadow(0 0 8px hsl(${hue}, 80%, 60%))`);
    }

    if (filters.length > 0) {
        img.style.filter = filters.join(' ');
    }

    // Size scale (applied to the tile via transform)
    if (hamster.size_scale != null && hamster.size_scale !== 1.0) {
        tile.style.transform = `scale(${hamster.size_scale})`;
        tile.style.transformOrigin = 'center bottom';
    }

    // Flip (CSS scaleX)
    if (hamster.is_flipped) {
        img.style.transform = 'scaleX(-1)';
    }

    // Animation speed (modify the dance animation duration)
    if (hamster.anim_speed != null && hamster.anim_speed !== 1.0) {
        img.style.animationDuration = `${0.5 * hamster.anim_speed}s`;
    }

    // Accessory (emoji overlay)
    if (hamster.accessory) {
        const acc = document.createElement('span');
        acc.className = `accessory accessory-${hamster.accessory}`;
        acc.textContent = getAccessoryEmoji(hamster.accessory);
        tile.appendChild(acc);
    }

    // Click to open profile
    tile.addEventListener('click', (e) => {
        e.stopPropagation();
        openProfile(hamster.id);
    });

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
    const dancingCount = Math.min(hamsterList.length, DANCE_FLOOR_MAX);

    // Update counter bar
    document.getElementById('hamster-count').textContent = dancingCount;
    if (totalHamsterCount > DANCE_FLOOR_MAX) {
        const totalLabel = document.getElementById('hamster-total-label');
        const totalEl = document.getElementById('hamster-total');
        totalLabel.style.display = 'inline';
        totalEl.textContent = totalHamsterCount;
    }

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

    // Sort by most recently active for the dance floor
    hamsterList.sort((a, b) => new Date(b.last_active) - new Date(a.last_active));

    // Only show top DANCE_FLOOR_MAX on the floor
    const displayList = hamsterList.slice(0, DANCE_FLOOR_MAX);

    displayList.forEach(hamster => {
        floor.appendChild(renderHamster(hamster));
    });

    // Show overflow message if needed
    const overflowDiv = document.getElementById('dance-floor-overflow');
    if (totalHamsterCount > DANCE_FLOOR_MAX) {
        overflowDiv.style.display = 'block';
        document.getElementById('showing-count').textContent = dancingCount;
        document.getElementById('total-count-label').textContent = totalHamsterCount;
    } else {
        overflowDiv.style.display = 'none';
    }

    // Show browse trigger button if there are hamsters
    const browseTrigger = document.getElementById('browse-trigger');
    if (totalHamsterCount > 0 && browseTrigger) {
        browseTrigger.style.display = 'block';
    }
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
        // Fetch active hamsters for the dance floor and total count in parallel
        const [res, countRes] = await Promise.all([
            fetch(`${API_BASE}/api/hamsters?page=1&per_page=${DANCE_FLOOR_MAX}&sort=active`),
            fetch(`${API_BASE}/api/hamsters/count`)
        ]);
        if (!res.ok) return;
        const data = await res.json();
        hamsters = {};
        data.forEach(h => { hamsters[h.id] = h; });

        if (countRes.ok) {
            const countData = await countRes.json();
            totalHamsterCount = countData.count;
        } else {
            totalHamsterCount = data.length;
        }

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
        renderHitCounter(visitorCount);
    } catch (e) {
        console.error('Failed to record visit:', e);
    }
}

// ---- Hit Counter ----
function renderHitCounter(count) {
    const container = document.getElementById('hit-counter-digits');
    if (!container) return;
    const digits = String(count).padStart(6, '0');
    container.innerHTML = '';
    for (const d of digits) {
        const span = document.createElement('span');
        span.className = 'hit-digit';
        span.textContent = d;
        container.appendChild(span);
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

    eventSource.addEventListener('battle_started', (e) => {
        const battle = JSON.parse(e.data);
        addFeedEntry(`${battle.challenger_name} started BEEF with ${battle.defender_name}: "${battle.challenger_diss}"`);
        fetchBattles();
    });

    eventSource.addEventListener('battle_responded', (e) => {
        const battle = JSON.parse(e.data);
        addFeedEntry(`${battle.defender_name} clapped back at ${battle.challenger_name}: "${battle.defender_diss}"`);
        fetchBattles();
    });

    eventSource.addEventListener('battle_cheered', (e) => {
        fetchBattles();
    });

    eventSource.addEventListener('conga_joined', (e) => {
        fetchConga();
    });

    eventSource.addEventListener('conga_left', (e) => {
        fetchConga();
    });

    eventSource.addEventListener('hamster_woke', (e) => {
        const hamster = JSON.parse(e.data);
        addFeedEntry(`${hamster.name} woke up from the cuddle puddle! Rise and shine!`);
        fetchSleepy();
        fetchHamsters();
    });

    eventSource.onerror = () => {
        console.log('SSE connection lost, reconnecting in 5s...');
        setTimeout(connectSSE, 5000);
    };
}

// ---- Tabs & Copy Buttons ----
function initTabs() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Deactivate all tabs and panels
            tabs.forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(p => p.classList.remove('active'));

            // Activate clicked tab and its panel
            tab.classList.add('active');
            const panel = document.getElementById('tab-' + tab.dataset.tab);
            if (panel) panel.classList.add('active');
        });
    });
}

function copyCode(btn) {
    const codeBlock = btn.closest('.code-block');
    const pre = codeBlock.querySelector('pre');
    const text = pre.textContent;

    navigator.clipboard.writeText(text).then(() => {
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => {
            btn.textContent = 'Copy';
            btn.classList.remove('copied');
        }, 2000);
    }).catch(() => {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => {
            btn.textContent = 'Copy';
            btn.classList.remove('copied');
        }, 2000);
    });
}

// ---- Feed Toggle ----
function toggleFeed() {
    document.getElementById('activity-feed').classList.toggle('collapsed');
}

// ---- Browse Drawer ----
function toggleBrowse() {
    const drawer = document.getElementById('browse-drawer');
    const overlay = document.getElementById('browse-overlay');
    const isOpen = drawer.classList.contains('open');
    drawer.classList.toggle('open');
    overlay.classList.toggle('open');

    // Load first page when opening for the first time
    if (!isOpen && document.getElementById('browse-list').children.length === 0) {
        loadBrowsePage(1);
    }
}

// ---- Browse All Hamsters ----
async function loadBrowsePage(page) {
    if (page < 1) return;
    currentBrowsePage = page;

    const sort = document.getElementById('browse-sort').value;
    const perPage = 50;

    try {
        const res = await fetch(`${API_BASE}/api/hamsters?page=${page}&per_page=${perPage}&sort=${sort}`);
        if (!res.ok) return;
        const data = await res.json();

        const list = document.getElementById('browse-list');
        list.innerHTML = '';

        // Header row
        const header = document.createElement('div');
        header.className = 'browse-row browse-row-header';
        header.innerHTML = `
            <span class="browse-col-name">Name</span>
            <span class="browse-col-creator">Creator</span>
            <span class="browse-col-level">Lvl</span>
            <span class="browse-col-style">Dance</span>
            <span class="browse-col-active">Last Active</span>
        `;
        list.appendChild(header);

        if (data.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'browse-empty';
            empty.textContent = 'No hamsters found on this page.';
            list.appendChild(empty);
        } else {
            data.forEach(h => {
                const row = document.createElement('div');
                row.className = 'browse-row';
                row.style.cursor = 'pointer';

                const lastActive = new Date(h.last_active);
                const timeAgo = getTimeAgo(lastActive);

                row.innerHTML = `
                    <span class="browse-col-name">${escapeHtml(h.name)}</span>
                    <span class="browse-col-creator">${escapeHtml(h.creator || '-')}</span>
                    <span class="browse-col-level">${h.level || 1}</span>
                    <span class="browse-col-style">${escapeHtml(h.dance_style || 'default')}</span>
                    <span class="browse-col-active">${timeAgo}</span>
                `;
                row.addEventListener('click', () => openProfile(h.id));
                list.appendChild(row);
            });
        }

        // Update pagination controls
        document.getElementById('browse-page-info').textContent = `Page ${page}`;
        document.getElementById('browse-prev').disabled = (page <= 1);
        document.getElementById('browse-next').disabled = (data.length < perPage);

    } catch (e) {
        console.error('Failed to load browse page:', e);
    }
}

function getTimeAgo(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
}

// ---- Search ----
let searchTimeout = null;

function initSearch() {
    const input = document.getElementById('search-input');
    const results = document.getElementById('search-results');

    input.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        const q = input.value.trim();
        if (!q) {
            results.style.display = 'none';
            clearSearchHighlights();
            return;
        }
        searchTimeout = setTimeout(() => performSearch(q), 250);
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            doSearch();
        }
        if (e.key === 'Escape') {
            results.style.display = 'none';
            clearSearchHighlights();
        }
    });

    // Close results when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#search-bar')) {
            results.style.display = 'none';
        }
    });
}

function doSearch() {
    const q = document.getElementById('search-input').value.trim();
    if (q) performSearch(q);
}

async function performSearch(query) {
    const results = document.getElementById('search-results');
    try {
        const res = await fetch(`${API_BASE}/api/hamsters/search?q=${encodeURIComponent(query)}`);
        if (!res.ok) return;
        const data = await res.json();

        clearSearchHighlights();

        if (data.length === 0) {
            results.innerHTML = '<div class="search-no-results">No hampsters found!</div>';
            results.style.display = 'block';
            return;
        }

        results.innerHTML = '';
        data.forEach(h => {
            const item = document.createElement('div');
            item.className = 'search-result-item';

            // Highlight on dance floor if visible
            const tile = document.getElementById(`hamster-${h.id}`);
            if (tile) {
                tile.classList.add('search-highlight');
            }

            item.innerHTML = `
                <img src="${getHamsterGif(h)}" alt="">
                <span class="search-result-name">${escapeHtml(h.name)}</span>
                <span class="search-result-creator">${h.creator ? 'by ' + escapeHtml(h.creator) : ''}</span>
                <span class="search-result-style">${h.dance_style || 'default'}</span>
            `;
            item.addEventListener('click', () => {
                results.style.display = 'none';
                clearSearchHighlights();
                openProfile(h.id);
            });
            results.appendChild(item);
        });

        results.style.display = 'block';
    } catch (e) {
        console.error('Search failed:', e);
    }
}

function clearSearchHighlights() {
    document.querySelectorAll('.search-highlight').forEach(el => {
        el.classList.remove('search-highlight');
    });
}

// ---- Hamster Profile ----
let currentProfileId = null;

async function openProfile(hamsterId) {
    currentProfileId = hamsterId;
    const overlay = document.getElementById('profile-overlay');
    overlay.style.display = 'flex';

    // Fetch hamster data, activity, and follower count in parallel
    try {
        const [hamsterRes, activityRes, followerRes] = await Promise.all([
            fetch(`${API_BASE}/api/hamsters/${hamsterId}`),
            fetch(`${API_BASE}/api/hamsters/${hamsterId}/activity?limit=50`),
            fetch(`${API_BASE}/api/hamsters/${hamsterId}/followers/count`),
        ]);

        if (!hamsterRes.ok) {
            closeProfile();
            return;
        }

        const hamster = await hamsterRes.json();
        const activity = activityRes.ok ? await activityRes.json() : [];
        const followerData = followerRes.ok ? await followerRes.json() : { count: 0 };

        renderProfile(hamster, activity, followerData.count);
    } catch (e) {
        console.error('Failed to load profile:', e);
        closeProfile();
    }
}

function renderProfile(hamster, activity, followerCount) {
    // Title bar
    document.getElementById('profile-title').textContent = hamster.name + ' - Hamster Profile';

    // Header
    const profileGif = document.getElementById('profile-gif');
    profileGif.src = getHamsterGif(hamster);
    // Apply trait filters to profile GIF
    const profileFilters = [];
    if (hamster.body_hue != null && hamster.body_hue !== 0) {
        profileFilters.push(`hue-rotate(${hamster.body_hue}deg)`);
    }
    if (hamster.has_glow) {
        const hue = hamster.body_hue || 0;
        profileFilters.push(`drop-shadow(0 0 8px hsl(${hue}, 80%, 60%))`);
    }
    profileGif.style.filter = profileFilters.length > 0 ? profileFilters.join(' ') : '';
    profileGif.style.transform = hamster.is_flipped ? 'scaleX(-1)' : '';

    document.getElementById('profile-name').textContent = hamster.name;
    document.getElementById('profile-creator').textContent = hamster.creator ? 'Created by: ' + hamster.creator : '';
    document.getElementById('profile-dance').textContent = 'Dance: ' + (hamster.dance_style || 'default');

    // Traits display
    const HUE_NAMES = {0:'Golden',30:'Rose',50:'Coral',80:'Crimson',120:'Purple',160:'Indigo',200:'Teal',220:'Cyan',250:'Forest',290:'Lime',320:'Mint'};
    const SIZE_NAMES = {0.7:'Tiny',0.85:'Small',1.0:'Normal',1.15:'Large',1.3:'Chonky'};
    const SPEED_NAMES = {1.5:'Chill',1.0:'Normal',0.6:'Hyper',0.3:'Frantic'};
    const hueName = HUE_NAMES[hamster.body_hue] || 'Unknown';
    const sizeName = SIZE_NAMES[hamster.size_scale] || 'Normal';
    const speedName = SPEED_NAMES[hamster.anim_speed] || 'Normal';
    let traitsStr = `${hueName} ${sizeName} | GIF #${hamster.base_gif || '?'} | ${speedName}`;
    if (hamster.has_glow) traitsStr += ' | GLOW';
    if (hamster.is_flipped) traitsStr += ' | Flipped';

    const accessoryEl = document.getElementById('profile-accessory');
    accessoryEl.innerHTML = '';
    if (hamster.accessory) {
        accessoryEl.textContent = 'Accessory: ' + getAccessoryEmoji(hamster.accessory) + ' ' + hamster.accessory;
    }

    document.getElementById('profile-level').textContent = `Level ${hamster.level || 1} | ${traitsStr}`;

    // Zodiac sign
    const zodiacEl = document.getElementById('profile-zodiac');
    if (zodiacEl) {
        const sign = getZodiacSign(hamster.created_at);
        zodiacEl.textContent = 'Zodiac: ' + sign;
    }

    // Bio
    const bioEl = document.getElementById('profile-bio');
    if (hamster.bio) {
        bioEl.textContent = hamster.bio;
        bioEl.style.display = 'block';
    } else {
        bioEl.style.display = 'none';
    }

    // Stats
    document.getElementById('stat-messages').textContent = hamster.total_messages || 0;
    document.getElementById('stat-pokes-given').textContent = hamster.total_pokes_given || 0;
    document.getElementById('stat-pokes-received').textContent = hamster.total_pokes_received || 0;
    document.getElementById('stat-followers').textContent = followerCount;

    // Time on floor
    const created = new Date(hamster.created_at);
    const now = new Date();
    const diffMs = now - created;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffDays > 0) {
        document.getElementById('stat-age').textContent = diffDays + 'd';
    } else {
        document.getElementById('stat-age').textContent = diffHours + 'h';
    }

    // Activity feed
    const activityEl = document.getElementById('profile-activity');
    if (activity.length === 0) {
        activityEl.innerHTML = '<div class="activity-empty">No activity recorded yet.</div>';
    } else {
        activityEl.innerHTML = '';
        activity.forEach(a => {
            const entry = document.createElement('div');
            entry.className = 'activity-entry';
            const time = new Date(a.timestamp);
            const timeStr = time.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
            const description = formatActivity(a);
            entry.innerHTML = `<span class="activity-time">[${timeStr}]</span> ${escapeHtml(description)}`;
            activityEl.appendChild(entry);
        });
    }

    // Reset follow form
    document.getElementById('follow-form').style.display = 'flex';
    document.getElementById('follow-status').style.display = 'none';
    document.getElementById('follow-status').style.color = '';
    document.getElementById('follow-status').style.background = '';
    document.getElementById('follow-status').style.borderColor = '';
    document.getElementById('follow-email').value = '';
}

function formatActivity(activity) {
    switch (activity.action_type) {
        case 'joined':
            return 'Joined the dance floor' + (activity.detail ? ' (' + activity.detail + ')' : '');
        case 'said':
            return 'Said: "' + (activity.detail || '') + '"';
        case 'danced':
            return 'Started doing the ' + (activity.detail || 'default');
        case 'poked':
            return 'Poked ' + (activity.detail || 'someone');
        case 'was_poked':
            return 'Got poked by ' + (activity.detail || 'someone');
        case 'set_bio':
            return 'Updated their bio';
        case 'diss_started':
            return 'Started beef: ' + (activity.detail || '');
        case 'diss_received':
            return 'Got dissed: ' + (activity.detail || '');
        case 'diss_responded':
            return 'Clapped back: ' + (activity.detail || '');
        case 'conga_joined':
            return 'Joined the conga line!';
        case 'conga_left':
            return 'Left the conga line';
        case 'woke_up':
            return 'Woke up from the cuddle puddle!';
        default:
            return activity.action_type + (activity.detail ? ': ' + activity.detail : '');
    }
}

function closeProfile() {
    document.getElementById('profile-overlay').style.display = 'none';
    currentProfileId = null;
}

function closeProfileOverlay(event) {
    if (event.target === event.currentTarget) {
        closeProfile();
    }
}

// ---- Follow ----
async function followHamster() {
    if (!currentProfileId) return;
    const emailInput = document.getElementById('follow-email');
    const email = emailInput.value.trim();

    if (!email || !email.includes('@') || !email.includes('.')) {
        emailInput.style.borderColor = '#CC0000';
        setTimeout(() => { emailInput.style.borderColor = ''; }, 2000);
        return;
    }

    const btn = document.getElementById('follow-btn');
    btn.textContent = '...';
    btn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/api/hamsters/${currentProfileId}/follow`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email }),
        });

        const status = document.getElementById('follow-status');
        if (res.ok) {
            document.getElementById('follow-form').style.display = 'none';
            status.textContent = "You're following this hamster!";
            status.style.color = '#009900';
            status.style.background = '#F0FFF0';
            status.style.borderColor = '#99CC99';
            status.style.display = 'block';
            // Update follower count
            const countEl = document.getElementById('stat-followers');
            countEl.textContent = parseInt(countEl.textContent) + 1;
        } else {
            const data = await res.json();
            status.textContent = data.error || 'Something went wrong.';
            status.style.color = '#CC0000';
            status.style.background = '#FFF0F0';
            status.style.borderColor = '#CC9999';
            status.style.display = 'block';
        }
    } catch (e) {
        console.error('Follow failed:', e);
    } finally {
        btn.textContent = 'Follow!';
        btn.disabled = false;
    }
}

// ---- Zodiac Sign Helper ----
function getZodiacSign(createdAt) {
    try {
        const dt = new Date(createdAt);
        const month = dt.getMonth() + 1;
        const day = dt.getDate();
        const signs = [
            [1, 20, 'Aquarius'], [2, 19, 'Pisces'], [3, 21, 'Aries'],
            [4, 20, 'Taurus'], [5, 21, 'Gemini'], [6, 21, 'Cancer'],
            [7, 23, 'Leo'], [8, 23, 'Virgo'], [9, 23, 'Libra'],
            [10, 23, 'Scorpio'], [11, 22, 'Sagittarius'], [12, 22, 'Capricorn'],
        ];
        for (let i = signs.length - 1; i >= 0; i--) {
            if (month > signs[i][0] || (month === signs[i][0] && day >= signs[i][1])) {
                return signs[i][2];
            }
        }
        return 'Capricorn';
    } catch (e) {
        return 'Aries';
    }
}

// ---- Battles (Beef Zone) ----
async function fetchBattles() {
    try {
        const res = await fetch(`${API_BASE}/api/battles`);
        if (!res.ok) return;
        const battles = await res.json();
        renderBattles(battles);
    } catch (e) {
        console.error('Failed to fetch battles:', e);
    }
}

function renderBattles(battles) {
    const zone = document.getElementById('beef-zone');
    const container = document.getElementById('beef-battles');
    if (!zone || !container) return;
    if (battles.length === 0) { zone.style.display = 'none'; return; }
    zone.style.display = 'block';
    container.innerHTML = '';
    battles.slice(0, 5).forEach(b => {
        const card = document.createElement('div');
        card.className = 'battle-card';
        const cWin = b.cheers_challenger > b.cheers_defender;
        const dWin = b.cheers_defender > b.cheers_challenger;
        card.innerHTML = `
            <div class="battle-vs">
                <div class="battle-side ${cWin ? 'winning' : ''}">
                    <img src="${getHamsterGif(b.challenger_id)}" alt="" class="battle-hamster-gif">
                    <div class="battle-name">${escapeHtml(b.challenger_name)}</div>
                    <div class="battle-diss">"${escapeHtml(b.challenger_diss)}"</div>
                    <div class="battle-cheers" onclick="cheerBattle('${b.id}','challenger')">&#x1F44F; ${b.cheers_challenger}</div>
                </div>
                <div class="battle-divider">VS</div>
                <div class="battle-side ${dWin ? 'winning' : ''}">
                    <img src="${getHamsterGif(b.defender_id)}" alt="" class="battle-hamster-gif">
                    <div class="battle-name">${escapeHtml(b.defender_name)}</div>
                    <div class="battle-diss">${b.defender_diss ? '"'+escapeHtml(b.defender_diss)+'"' : '<em>awaiting response...</em>'}</div>
                    <div class="battle-cheers" onclick="cheerBattle('${b.id}','defender')">&#x1F44F; ${b.cheers_defender}</div>
                </div>
            </div>
            <div class="battle-status">${b.status==='complete' ? 'BATTLE COMPLETE' : 'OPEN - waiting for clap back!'}</div>`;
        container.appendChild(card);
    });
}

async function cheerBattle(battleId, side) {
    try { await fetch(`${API_BASE}/api/battles/${battleId}/cheer`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({side}) }); } catch(e) { console.error('Cheer failed:',e); }
}

// ---- Conga Line ----
async function fetchConga() {
    try {
        const res = await fetch(`${API_BASE}/api/conga`);
        if (!res.ok) return;
        renderConga(await res.json());
    } catch (e) { console.error('Failed to fetch conga:', e); }
}

function renderConga(data) {
    const section = document.getElementById('conga-section');
    const line = document.getElementById('conga-line');
    const countEl = document.getElementById('conga-count');
    if (!section || !line) return;
    if (!data.hamsters || data.hamsters.length < 2) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    countEl.textContent = data.count;
    line.innerHTML = '';
    line.style.animationDuration = Math.max(3, 15 - data.count * 1.5) + 's';
    data.hamsters.forEach((h, i) => {
        const d = document.createElement('div');
        d.className = 'conga-hamster';
        d.style.animationDelay = (i * 0.15) + 's';
        d.innerHTML = `<img src="${getHamsterGif(h.hamster_id)}" alt="${escapeHtml(h.name)}"><div class="conga-name">${escapeHtml(h.name)}</div>`;
        line.appendChild(d);
    });
}

// ---- Cuddle Puddle ----
async function fetchSleepy() {
    try {
        const res = await fetch(`${API_BASE}/api/hamsters/sleepy`);
        if (!res.ok) return;
        renderSleepy(await res.json());
    } catch (e) { console.error('Failed to fetch sleepy:', e); }
}

function renderSleepy(sleepy) {
    const section = document.getElementById('cuddle-puddle');
    const container = document.getElementById('cuddle-hamsters');
    if (!section || !container) return;
    if (sleepy.length === 0) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    container.innerHTML = '';
    sleepy.forEach((h, i) => {
        const d = document.createElement('div');
        d.className = 'cuddle-hamster';
        if (i > 0) d.style.marginLeft = '-25px';
        d.innerHTML = `<img src="${getHamsterGif(h)}" alt="${escapeHtml(h.name)}"><div class="zzz">zzz</div><div class="cuddle-name">${escapeHtml(h.name)}</div>`;
        container.appendChild(d);
    });
}

// ---- Horoscopes ----
async function fetchHoroscopes() {
    try {
        const res = await fetch(`${API_BASE}/api/horoscopes/today`);
        if (!res.ok) return;
        renderHoroscopes(await res.json());
    } catch (e) { console.error('Failed to fetch horoscopes:', e); }
}

function renderHoroscopes(horoscopes) {
    const section = document.getElementById('horoscope-section');
    const list = document.getElementById('horoscope-list');
    if (!section || !list) return;
    if (horoscopes.length === 0) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    list.innerHTML = '';
    const sym = {Aries:'\u2648',Taurus:'\u2649',Gemini:'\u264A',Cancer:'\u264B',Leo:'\u264C',Virgo:'\u264D',Libra:'\u264E',Scorpio:'\u264F',Sagittarius:'\u2650',Capricorn:'\u2651',Aquarius:'\u2652',Pisces:'\u2653'};
    horoscopes.forEach(h => {
        const c = document.createElement('div');
        c.className = 'horoscope-card';
        c.innerHTML = `<div class="horoscope-sign">${sym[h.sign]||'?'} ${escapeHtml(h.sign)}</div><div class="horoscope-text">${escapeHtml(h.horoscope)}</div>`;
        list.appendChild(c);
    });
}

// ---- Init ----
async function init() {
    updateMuteButton();
    await Promise.all([fetchHamsters(), fetchFeed(), recordVisit()]);
    connectSSE();
    initTabs();
    initSearch();
    fetchBattles();
    fetchConga();
    fetchSleepy();
    fetchHoroscopes();
    const browseTrigger = document.getElementById('browse-trigger');
    if (browseTrigger && totalHamsterCount === 0) browseTrigger.style.display = 'none';
    setInterval(fetchHamsters, 30000);
    setInterval(fetchBattles, 30000);
    setInterval(fetchConga, 30000);
    setInterval(fetchSleepy, 60000);
}

// ---- Changelog Modal ----
function toggleChangelog() {
    const overlay = document.getElementById('changelog-overlay');
    if (overlay.style.display === 'none' || !overlay.style.display) {
        overlay.style.display = 'flex';
    } else {
        overlay.style.display = 'none';
    }
}

function closeChangelogOverlay(event) {
    if (event.target === event.currentTarget) {
        toggleChangelog();
    }
}

init();
