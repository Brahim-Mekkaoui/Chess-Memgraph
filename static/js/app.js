/**
 * app.js — Gestionnaire d'Ouvertures d'Échecs
 * --------------------------------------------
 * Gère : échiquier interactif (chess.js + chessboard.js),
 *        appels API REST Flask, affichage des résultats,
 *        CRUD ouvertures (modal), notifications.
 *
 * Dépendances (chargées via CDN dans les templates) :
 *   - chess.js  v1.0.0-beta.6
 *   - chessboard.js  v1.0.0
 *   - Bootstrap 5
 */

/* ==========================================================================
   CONFIG
   ========================================================================== */
const API_BASE = '/api';

/* ==========================================================================
   NOTIFICATIONS (toasts)
   ========================================================================== */

/**
 * Affiche une notification flottante.
 * @param {string} message  Texte du message
 * @param {'success'|'error'|'info'|'warning'} type
 * @param {number} duration  Durée en ms (défaut : 3500)
 */
function showToast(message, type = 'info', duration = 3500) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const toast = document.createElement('div');
  toast.className = `app-toast ${type}`;
  toast.innerHTML = `<span>${icons[type] || ''} ${message}</span>`;
  container.appendChild(toast);

  // Auto-suppression
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(40px)';
    toast.style.transition = '.3s ease';
    setTimeout(() => toast.remove(), 350);
  }, duration);
}


/* ==========================================================================
   API — fonctions fetch centralisées
   ========================================================================== */

/**
 * Appel GET vers l'API.
 * @returns {Promise<object>}
 */
async function apiGet(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/**
 * Appel POST / PUT / DELETE vers l'API avec body JSON.
 */
async function apiCall(method, endpoint, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API_BASE}${endpoint}`, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}


/* ==========================================================================
   ÉCHIQUIER INTERACTIF (page index.html)
   ========================================================================== */

/** Variables globales pour chess.js et chessboard.js */
let game   = null;   // instance chess.js
let board  = null;   // instance chessboard.js
let detectTimeout = null;  // debounce pour la détection

/**
 * Initialise l'échiquier si le div #chess-board est présent dans la page.
 */
function initBoard() {
  const boardEl = document.getElementById('chess-board');
  if (!boardEl) return;

  // Vérifier que chess.js et chessboard.js sont chargés
  if (typeof Chess === 'undefined' || typeof Chessboard === 'undefined') {
    console.error('chess.js ou chessboard.js non chargé !');
    return;
  }

  game = new Chess();

  board = Chessboard('chess-board', {
    draggable   : true,
    position    : 'start',
    pieceTheme  : 'https://chessboardjs.com/img/chesspieces/wikipedia/{piece}.png',
    onDragStart : onDragStart,
    onDrop      : onDrop,
    onSnapEnd   : onSnapEnd,
  });

  // Boutons de contrôle
  document.getElementById('btn-reset')?.addEventListener('click', resetBoard);
  document.getElementById('btn-flip')?.addEventListener('click', () => board.flip());
  document.getElementById('btn-undo')?.addEventListener('click', undoMove);

  // Mettre à jour l'affichage initial
  updateStatus();
}

/** Empêche de déplacer une pièce si ce n'est pas son tour ou si la partie est finie. */
function onDragStart(source, piece, position, orientation) {
  if (game.game_over()) return false;
  if ((game.turn() === 'w' && piece.search(/^b/) !== -1) ||
      (game.turn() === 'b' && piece.search(/^w/) !== -1)) return false;
}

/** Gère le dépôt d'une pièce — valide le coup et met à jour l'affichage. */
function onDrop(source, target) {
  const move = game.move({
    from      : source,
    to        : target,
    promotion : 'q', // toujours promouvoir en dame (simplification UI)
  });

  // Coup illégal → retour à la position d'origine
  if (move === null) return 'snapback';

  updateStatus();
  triggerOpeningDetect();
}

/** Synchronise l'affichage chessboard.js après animation. */
function onSnapEnd() {
  board.position(game.fen());
}

/** Remet l'échiquier en position initiale. */
function resetBoard() {
  game.reset();
  board.start();
  clearOpeningInfo();
  updateStatus();
}

/** Annule le dernier demi-coup. */
function undoMove() {
  game.undo();
  board.position(game.fen());
  clearOpeningInfo();
  updateStatus();
  triggerOpeningDetect();
}

/** Met à jour le texte de statut sous l'échiquier. */
function updateStatus() {
  const statusEl = document.getElementById('board-status');
  if (!statusEl) return;

  let status = '';
  const turn = game.turn() === 'w' ? 'Blancs' : 'Noirs';

  if (game.in_checkmate()) {
    status = `Échec et mat ! ${turn === 'Blancs' ? 'Noirs' : 'Blancs'} gagnent.`;
  } else if (game.in_draw()) {
    status = 'Nulle !';
  } else {
    status = `Trait aux ${turn}`;
    if (game.in_check()) status += ' — Échec !';
  }

  statusEl.textContent = status;
}

/** Lance la détection d'ouverture avec un délai (debounce 300 ms). */
function triggerOpeningDetect() {
  clearTimeout(detectTimeout);
  detectTimeout = setTimeout(detectOpening, 300);
}

/**
 * Appelle l'API /api/detect?fen=... pour identifier l'ouverture
 * et met à jour le panneau d'information.
 */
async function detectOpening() {
  const fen = game.fen();

  // Position initiale → rien à détecter
  if (fen === 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1') {
    clearOpeningInfo();
    return;
  }

  try {
    const data = await apiGet(`/detect?fen=${encodeURIComponent(fen)}`);

    if (data.found) {
      displayOpeningInfo(data.opening);
      loadSimilarOpenings(data.opening.id);
    } else {
      // Essayer avec la séquence de coups
      const history = game.history().join(' ');
      if (history) detectByMoves(history);
      else displayOpeningNotFound();
    }
  } catch (err) {
    console.warn('Détection FEN échouée, tentative par coups…', err);
    displayOpeningNotFound();
  }
}

/** Détection par séquence de coups (fallback). */
async function detectByMoves(moves) {
  try {
    const data = await apiGet(`/moves?moves=${encodeURIComponent(moves)}`);
    if (data.found) {
      displayOpeningInfo(data.opening);
      loadSimilarOpenings(data.opening.id);
    } else {
      displayOpeningNotFound();
    }
  } catch (err) {
    displayOpeningNotFound();
  }
}

/** Affiche les informations d'une ouverture dans le panneau. */
function displayOpeningInfo(opening) {
  const panel = document.getElementById('opening-info-panel');
  if (!panel) return;

  panel.innerHTML = `
    <div class="opening-found">
      <div class="d-flex align-items-center gap-2 mb-2">
        <span class="eco-badge">${escHtml(opening.eco_code)}</span>
        <strong>${escHtml(opening.name)}</strong>
      </div>
      ${opening.variant ? `<div class="text-muted small mb-2">Variante : ${escHtml(opening.variant)}</div>` : ''}
      <div class="moves-display mb-2">${escHtml(opening.moves || opening.moves_raw || '')}</div>
      <a href="/opening/${opening.id}" class="btn btn-sm btn-outline-primary">
        Voir détail →
      </a>
    </div>
    <div id="similar-panel" class="mt-3">
      <small class="text-muted fw-bold">Ouvertures similaires :</small>
      <div id="similar-list-container" class="mt-1">
        <div class="spinner-chess mx-auto d-block mt-2" style="width:1.5rem;height:1.5rem;border-width:3px;"></div>
      </div>
    </div>
  `;
}

/** Affiche "aucune ouverture trouvée". */
function displayOpeningNotFound() {
  const panel = document.getElementById('opening-info-panel');
  if (!panel) return;
  panel.innerHTML = `
    <div class="opening-not-found">
      <div style="font-size:2rem">♟️</div>
      <p class="mt-2 mb-0">Aucune ouverture répertoriée pour cette position.</p>
      <small>Continuez à jouer…</small>
    </div>
  `;
}

/** Vide le panneau d'information. */
function clearOpeningInfo() {
  const panel = document.getElementById('opening-info-panel');
  if (!panel) return;
  panel.innerHTML = `
    <div class="opening-not-found">
      <div style="font-size:2.5rem">♟️</div>
      <p class="mt-2 mb-0 fw-bold">Jouez un coup pour détecter l'ouverture.</p>
    </div>
  `;
}

/**
 * Charge et affiche les ouvertures similaires à partir de l'API.
 */
async function loadSimilarOpenings(openingId) {
  const container = document.getElementById('similar-list-container');
  if (!container) return;

  try {
    const data = await apiGet(`/similar/${openingId}?depth=2`);
    const similars = data.similar || [];

    if (similars.length === 0) {
      container.innerHTML = `<small class="text-muted">Aucune ouverture similaire trouvée.</small>`;
      return;
    }

    const items = similars.slice(0, 6).map(s => `
      <li onclick="window.location='/opening/${s.id}'" title="${escHtml(s.moves_raw || '')}">
        <span class="eco-mini">${escHtml(s.eco_code)}</span>
        <span class="small">${escHtml(s.name)}</span>
      </li>
    `).join('');

    container.innerHTML = `<ul class="similar-list">${items}</ul>`;
  } catch (err) {
    container.innerHTML = `<small class="text-danger">Erreur chargement.</small>`;
  }
}


/* ==========================================================================
   PAGE LISTE DES OUVERTURES (/openings)
   ========================================================================== */

/**
 * Initialise la page liste :
 *   - filtre de recherche en temps réel
 *   - filtres par famille ECO (A/B/C/D/E)
 *   - bouton de création
 */
function initOpeningsList() {
  const listContainer = document.getElementById('openings-grid');
  if (!listContainer) return;

  // Recherche live
  const searchBar = document.getElementById('search-bar');
  searchBar?.addEventListener('input', () => {
    filterOpenings(searchBar.value.trim().toLowerCase());
  });

  // Filtres ECO
  document.querySelectorAll('.eco-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.eco-filter-btn').forEach(b => b.classList.remove('active', 'btn-primary'));
      btn.classList.add('active', 'btn-primary');
      const family = btn.dataset.eco || '';
      filterOpenings('', family);
    });
  });

  // Bouton créer
  document.getElementById('btn-create-opening')?.addEventListener('click', () => {
    openCrudModal(null);
  });
}

/** Filtre les cartes d'ouvertures dans la grille. */
function filterOpenings(query = '', ecoFamily = '') {
  document.querySelectorAll('.opening-card-wrapper').forEach(wrapper => {
    const name = (wrapper.dataset.name || '').toLowerCase();
    const eco  = (wrapper.dataset.eco  || '').toLowerCase();

    const matchQuery  = !query     || name.includes(query) || eco.includes(query);
    const matchFamily = !ecoFamily || eco.startsWith(ecoFamily.toLowerCase());

    wrapper.style.display = (matchQuery && matchFamily) ? '' : 'none';
  });
}


/* ==========================================================================
   MODAL CRUD (créer / modifier ouverture)
   ========================================================================== */

/** Ouvre la modal de création ou d'édition.
 *  @param {object|null} opening  null = création, objet = édition
 */
function openCrudModal(opening) {
  const modalEl = document.getElementById('crud-modal');
  if (!modalEl) return;

  // Récupérer l'instance existante ou en créer une nouvelle
  let modal = bootstrap.Modal.getInstance(modalEl);
  if (!modal) {
    modal = new bootstrap.Modal(modalEl);
  }

  // Titre
  modalEl.querySelector('#modal-title').textContent =
    opening ? `Modifier : ${opening.name}` : 'Nouvelle ouverture';

  // Pré-remplissage des champs
  const fields = ['name', 'eco_code', 'moves', 'moves_raw', 'variant', 'fen'];
  fields.forEach(f => {
    const el = modalEl.querySelector(`#field-${f}`);
    if (el) el.value = opening ? (opening[f] || '') : '';
  });

  // ID caché pour savoir si c'est un edit
  modalEl.querySelector('#field-id').value = opening ? opening.id : '';

  modal.show();
}

/** Soumet le formulaire CRUD (création ou mise à jour). */
async function submitCrudForm() {
  const modalEl = document.getElementById('crud-modal');
  const id = modalEl.querySelector('#field-id').value;

  const payload = {
    name      : modalEl.querySelector('#field-name').value.trim(),
    eco_code  : modalEl.querySelector('#field-eco_code').value.trim().toUpperCase(),
    moves     : modalEl.querySelector('#field-moves').value.trim(),
    moves_raw : modalEl.querySelector('#field-moves_raw').value.trim(),
    variant   : modalEl.querySelector('#field-variant').value.trim(),
    fen       : modalEl.querySelector('#field-fen').value.trim(),
  };

  if (!payload.name || !payload.eco_code) {
    showToast('Le nom et le code ECO sont obligatoires.', 'warning');
    return;
  }

  try {
    if (id) {
      // Mise à jour
      await apiCall('PUT', `/opening/${id}`, payload);
      showToast('Ouverture mise à jour avec succès.', 'success');
    } else {
      // Création
      await apiCall('POST', '/opening', payload);
      showToast('Ouverture créée avec succès.', 'success');
    }

    // Fermer la modal et recharger la page
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
    setTimeout(() => location.reload(), 800);
  } catch (err) {
    showToast(`Erreur : ${err.message}`, 'error');
  }
}

/** Supprime une ouverture après confirmation. */
async function deleteOpening(openingId, openingName) {
  if (!confirm(`Supprimer "${openingName}" ? Cette action est irréversible.`)) return;

  try {
    await apiCall('DELETE', `/opening/${openingId}`);
    showToast('Ouverture supprimée.', 'success');
    setTimeout(() => {
      // Retourner à la liste ou recharger
      if (window.location.pathname.includes('/opening/')) {
        window.location = '/openings';
      } else {
        location.reload();
      }
    }, 800);
  } catch (err) {
    showToast(`Erreur : ${err.message}`, 'error');
  }
}

/* ==========================================================================
   MINI-ÉCHIQUIER (page détail)
   ========================================================================== */

/**
 * Affiche une position FEN sur un mini-échiquier statique.
 * @param {string} elementId   ID du div cible
 * @param {string} fen         Position FEN à afficher
 */
function initMiniBoard(elementId, fen) {
  if (typeof Chessboard === 'undefined') return;

  Chessboard(elementId, {
    position    : fen || 'start',
    draggable   : false,
    pieceTheme  : 'https://chessboardjs.com/img/chesspieces/wikipedia/{piece}.png',
  });
}


/* ==========================================================================
   GRAPHE vis.js (page graph_view.html)
   ========================================================================== */

let networkInstance = null;  // référence à l'instance vis.js Network

/** Couleurs des groupes ECO */
const ECO_COLORS = {
  A: { bg: '#1565c0', border: '#4fc3f7', font: '#e3f2fd' },
  B: { bg: '#2e7d32', border: '#81c784', font: '#e8f5e9' },
  C: { bg: '#b71c1c', border: '#e57373', font: '#ffebee' },
  D: { bg: '#e65100', border: '#ffb74d', font: '#fff8e1' },
  E: { bg: '#6a1b9a', border: '#ce93d8', font: '#f3e5f5' },
};

/**
 * Initialise et rend le graphe vis.js.
 * Récupère les données depuis /api/graph-data.
 */
async function initGraph() {
  const container = document.getElementById('graph-container');
  if (!container) return;

  // Afficher un spinner pendant le chargement
  container.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:center;height:100%;color:#aaa;">
      <div>
        <div class="spinner-chess mx-auto d-block" style="border-top-color:#4fc3f7;"></div>
        <p class="mt-3">Chargement du graphe…</p>
      </div>
    </div>
  `;

  try {
    const data = await apiGet('/graph-data');
    renderGraph(container, data.nodes, data.edges);
    updateGraphStats(data.nodes.length, data.edges.length);
  } catch (err) {
    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;height:100%;color:#e57373;">
        <div class="text-center">
          <div style="font-size:3rem">⚠️</div>
          <p>Erreur de chargement : ${err.message}</p>
          <button class="btn btn-sm btn-outline-light" onclick="initGraph()">Réessayer</button>
        </div>
      </div>
    `;
  }
}

/**
 * Rend le graphe avec vis.js Network.
 */
function renderGraph(container, nodes, edges) {
  if (typeof vis === 'undefined') {
    container.innerHTML = '<p class="text-danger text-center p-4">vis.js non chargé.</p>';
    return;
  }

  // Transformer les nœuds pour vis.js
  const visNodes = new vis.DataSet(nodes.map(n => {
    const ecoLetter = (n.eco_code || 'A')[0].toUpperCase();
    const color = ECO_COLORS[ecoLetter] || ECO_COLORS['A'];
    return {
      id    : n.id,
      label : `${n.eco_code}\n${truncate(n.name, 18)}`,
      title : buildNodeTooltip(n),  // tooltip HTML
      color : {
        background : color.bg,
        border     : color.border,
        highlight  : { background: '#fff', border: color.border },
        hover      : { background: lighten(color.bg), border: color.border },
      },
      font   : { color: color.font, size: 11 },
      shape  : 'ellipse',
      size   : 18,
      group  : ecoLetter,
      // données brutes pour le panneau d'info
      raw    : n,
    };
  }));

  // Transformer les arêtes pour vis.js
  const visEdges = new vis.DataSet(edges.map(e => ({
    from   : e.from,
    to     : e.to,
    color  : { color: '#555', highlight: '#aef', hover: '#aef' },
    arrows : { to: { enabled: true, scaleFactor: 0.6 } },
    width  : 1.5,
    smooth : { type: 'curvedCW', roundness: 0.15 },
  })));

  const options = {
    layout: {
      improvedLayout : true,
    },
    physics: {
      solver         : 'barnesHut',
      barnesHut      : { gravitationalConstant: -8000, springLength: 120 },
      stabilization  : { iterations: 150 },
    },
    interaction: {
      hover          : true,
      tooltipDelay   : 100,
      navigationButtons : false,
      keyboard       : true,
    },
    nodes: {
      borderWidth    : 2,
      borderWidthSelected : 4,
    },
    edges: {
      selectionWidth : 3,
    },
  };

  networkInstance = new vis.Network(container, { nodes: visNodes, edges: visEdges }, options);

  // Clic sur un nœud → afficher infos
  networkInstance.on('click', params => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      const node   = visNodes.get(nodeId);
      if (node) displayNodeInfo(node.raw);
    } else {
      clearNodeInfo();
    }
  });

  // Double-clic → aller à la page détail
  networkInstance.on('doubleClick', params => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      window.location = `/opening/${nodeId}`;
    }
  });
}

/** Construit le contenu HTML du tooltip vis.js. */
function buildNodeTooltip(n) {
  const div = document.createElement('div');
  div.style.cssText = 'padding:6px 10px;max-width:240px;';
  div.innerHTML = `
    <strong>${escHtml(n.name)}</strong><br>
    <span style="font-family:monospace;font-size:.8rem">${escHtml(n.eco_code)}</span>
    ${n.variant ? `<br><em style="font-size:.78rem">${escHtml(n.variant)}</em>` : ''}
    ${n.moves_raw ? `<br><code style="font-size:.72rem">${escHtml(n.moves_raw.substring(0, 40))}…</code>` : ''}
    <br><small style="color:#aaa">Double-clic pour détail</small>
  `;
  return div;
}

/** Affiche les infos du nœud sélectionné. */
function displayNodeInfo(n) {
  const panel = document.getElementById('node-info-panel');
  if (!panel) return;

  const ecoLetter = (n.eco_code || 'A')[0].toUpperCase();
  const color     = ECO_COLORS[ecoLetter] || ECO_COLORS['A'];

  panel.innerHTML = `
    <div class="d-flex align-items-center gap-2 mb-2">
      <span class="eco-badge" style="background:${color.bg}">${escHtml(n.eco_code)}</span>
      <strong>${escHtml(n.name)}</strong>
    </div>
    ${n.variant ? `<div class="text-muted small mb-1">Variante : ${escHtml(n.variant)}</div>` : ''}
    <div class="moves-display mb-2 small">${escHtml(n.moves_raw || n.moves || '—')}</div>
    <a href="/opening/${n.id}" class="btn btn-sm btn-outline-primary">
      Voir détail →
    </a>
  `;
}

/** Vide le panneau d'info nœud. */
function clearNodeInfo() {
  const panel = document.getElementById('node-info-panel');
  if (!panel) return;
  panel.innerHTML = `<p class="placeholder-text">Cliquez sur un nœud pour voir ses informations.</p>`;
}

/** Met à jour les compteurs de stats du graphe. */
function updateGraphStats(nNodes, nEdges) {
  const el = document.getElementById('graph-stats');
  if (el) el.textContent = `${nNodes} nœuds · ${nEdges} relations SIMILAR_TO`;
}

/** Contrôles du graphe (boutons toolbar). */
function graphFitAll() { networkInstance?.fit({ animation: true }); }
function graphStabilize() { networkInstance?.stabilize(); }
function graphZoomIn()  { if (!networkInstance) return; const s = networkInstance.getScale(); networkInstance.moveTo({ scale: s * 1.3 }); }
function graphZoomOut() { if (!networkInstance) return; const s = networkInstance.getScale(); networkInstance.moveTo({ scale: s * 0.75 }); }

/** Change le filtre de familles ECO affichées. */
function filterGraphByEco(ecoLetter) {
  if (!networkInstance) return;
  // Sélectionner tous les nœuds de la famille
  const allNodes = networkInstance.body.data.nodes;
  const toSelect = allNodes.getIds().filter(id => {
    const n = allNodes.get(id);
    return !ecoLetter || (n.group === ecoLetter);
  });
  networkInstance.selectNodes(toSelect);
  if (toSelect.length > 0) {
    networkInstance.fit({ nodes: toSelect, animation: true });
  }
}


/* ==========================================================================
   UTILITAIRES
   ========================================================================== */

/** Échappe le HTML pour éviter les injections XSS. */
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Tronque une chaîne avec '…'. */
function truncate(str, max = 30) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max) + '…' : str;
}

/** Éclaircit légèrement une couleur hex (pour l'effet hover). */
function lighten(hex) {
  try {
    const num = parseInt(hex.replace('#', ''), 16);
    const r = Math.min(255, ((num >> 16) & 0xff) + 40);
    const g = Math.min(255, ((num >>  8) & 0xff) + 40);
    const b = Math.min(255, ( num        & 0xff) + 40);
    return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`;
  } catch { return hex; }
}


/* ==========================================================================
   INITIALISATION AU CHARGEMENT DE LA PAGE
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
  // Activer le lien nav correspondant à la page courante
  const path = window.location.pathname;
  document.querySelectorAll('.nav-link').forEach(link => {
    if (link.getAttribute('href') === path ||
        (path.startsWith('/opening') && link.getAttribute('href') === '/openings')) {
      link.classList.add('active');
    }
  });

  // Initialiser le composant selon la page
  if (document.getElementById('chess-board'))  initBoard();
  if (document.getElementById('openings-grid')) initOpeningsList();
  if (document.getElementById('graph-container')) initGraph();

  // Exposer submitCrudForm globalement pour le bouton dans le modal
  window.submitCrudForm  = submitCrudForm;
  window.openCrudModal   = openCrudModal;
  window.deleteOpening   = deleteOpening;
  window.initMiniBoard   = initMiniBoard;
  window.graphFitAll     = graphFitAll;
  window.graphStabilize  = graphStabilize;
  window.graphZoomIn     = graphZoomIn;
  window.graphZoomOut    = graphZoomOut;
  window.filterGraphByEco = filterGraphByEco;
  window.showToast       = showToast;
});
