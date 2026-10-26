<script setup>
import { computed, onMounted, ref } from "vue";

const PENDING_SAVE_PREFIX = "resonance:pending-playlist:v1:";

const user = ref(null);
const libraries = ref([]);
const collections = ref([]);
const username = ref("");
const password = ref("");
const error = ref("");
const busy = ref(false);
const embeddingProfiles = ref([]);
const adminLibraryId = ref("");
const adminProfileId = ref("");
const newCollectionName = ref("");
const initialTrackLimit = ref("10");
const adminBusy = ref(false);
const adminError = ref("");
const adminMessage = ref("");
const adminMessageType = ref("info");

const selectedCollectionName = ref("");
const previousCollectionName = ref("");
const query = ref("");
const searchResults = ref([]);
const hasSearched = ref(false);
const searchBusy = ref(false);
const searchError = ref("");
const selectedTracks = ref([]);
const selectedLibraryId = ref(null);
const playlistName = ref("");
const allowDuplicateName = ref(false);

const pendingSave = ref(null);
const pendingSaveStatus = ref(null);
const completedSave = ref(null);
const saveBusy = ref(false);
const saveMessage = ref("");
const saveMessageType = ref("info");
const duplicateNameNeedsAcknowledgement = ref(false);

const authenticated = computed(() => user.value !== null);
const collectionsFor = (libraryId) => collections.value.filter((collection) => collection.library_id === libraryId);
const selectedCollection = computed(
  () => collections.value.find((collection) => collection.name === selectedCollectionName.value) || null,
);
const selectedLibrary = computed(
  () => libraries.value.find((library) => library.id === selectedCollection.value?.library_id) || null,
);
const selectedAdminProfile = computed(
  () => embeddingProfiles.value.find((profile) => profile.id === adminProfileId.value) || null,
);
const canSave = computed(
  () =>
    selectedTracks.value.length > 0 &&
    selectedTracks.value.length <= 100 &&
    playlistName.value.trim().length > 0 &&
    (!duplicateNameNeedsAcknowledgement.value || allowDuplicateName.value) &&
    !pendingSave.value &&
    !saveBusy.value,
);
const canReplayPendingSave = computed(
  () => pendingSaveStatus.value === "prepared" || pendingSaveStatus.value === "operation_not_found",
);
const needsManualReview = computed(
  () =>
    pendingSave.value &&
    !canReplayPendingSave.value &&
    pendingSaveStatus.value !== "verified" &&
    pendingSaveStatus.value !== "failed",
);

function pendingSaveKey(owner) {
  return `${PENDING_SAVE_PREFIX}${encodeURIComponent(owner)}`;
}

function clearDiscovery() {
  searchResults.value = [];
  hasSearched.value = false;
  searchError.value = "";
  selectedTracks.value = [];
  selectedLibraryId.value = null;
  selectedCollectionName.value = collections.value[0]?.name || "";
  previousCollectionName.value = selectedCollectionName.value;
  query.value = "";
  playlistName.value = "";
  allowDuplicateName.value = false;
}

function clearUserData() {
  user.value = null;
  libraries.value = [];
  collections.value = [];
  pendingSave.value = null;
  pendingSaveStatus.value = null;
  completedSave.value = null;
  saveMessage.value = "";
  duplicateNameNeedsAcknowledgement.value = false;
  embeddingProfiles.value = [];
  adminLibraryId.value = "";
  adminProfileId.value = "";
  adminError.value = "";
  adminMessage.value = "";
  clearDiscovery();
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login" && path !== "/api/auth/me") {
      clearUserData();
      error.value = "Your session expired. Sign in again.";
    }
    const reason = new Error(data?.detail || `Request failed (${response.status})`);
    reason.code = data?.code;
    reason.status = response.status;
    throw reason;
  }
  return data;
}

async function loadCollections() {
  collections.value = await request("/api/collections");
  if (!selectedCollectionName.value || !collections.value.some((item) => item.name === selectedCollectionName.value)) {
    selectedCollectionName.value = collections.value[0]?.name || "";
  }
  previousCollectionName.value = selectedCollectionName.value;
}

async function loadAdminSetup() {
  if (!user.value?.is_admin) return;
  adminError.value = "";
  try {
    embeddingProfiles.value = await request("/api/embedding-profiles");
    const defaultProfile = embeddingProfiles.value.find((profile) => profile.is_default);
    if (!embeddingProfiles.value.some((profile) => profile.id === adminProfileId.value)) {
      adminProfileId.value = defaultProfile?.id || embeddingProfiles.value[0]?.id || "";
    }
    if (!libraries.value.some((library) => library.id === adminLibraryId.value)) {
      adminLibraryId.value = libraries.value[0]?.id || "";
    }
  } catch (reason) {
    adminError.value = reason.message;
  }
}

async function restorePendingSave(owner) {
  const key = pendingSaveKey(owner);
  let restored;
  try {
    const stored = sessionStorage.getItem(key);
    if (!stored) return;
    restored = JSON.parse(stored);
  } catch {
    try {
      sessionStorage.removeItem(key);
    } catch {
      // Storage failure must not block login; no operation is retried automatically.
    }
    saveMessage.value = "A saved playlist operation could not be read and was cleared.";
    saveMessageType.value = "error";
    return;
  }

  if (
    restored?.owner !== owner ||
    typeof restored.operation_id !== "string" ||
    !restored.request ||
    typeof restored.request.library_id !== "string" ||
    typeof restored.request.name !== "string" ||
    !Array.isArray(restored.request.song_ids)
  ) {
    try {
      sessionStorage.removeItem(key);
    } catch {
      // Ignore malformed per-user state if storage is unavailable.
    }
    return;
  }

  pendingSave.value = restored;
  selectedTracks.value = restored.request.song_ids.map((songId) => ({ song_id: songId, title: songId, artist: "" }));
  selectedLibraryId.value = restored.request.library_id;
  playlistName.value = restored.request.name;
  allowDuplicateName.value = restored.request.allow_duplicate_name === true;
  const restoredCollection = collections.value.find((item) => item.library_id === restored.request.library_id);
  if (restoredCollection) {
    selectedCollectionName.value = restoredCollection.name;
    previousCollectionName.value = restoredCollection.name;
  }
  saveMessage.value = "Checking the last playlist save for this Navidrome account…";
  saveMessageType.value = "info";
  await checkPendingSave();
}

async function refresh() {
  const me = await request("/api/auth/me");
  const changedAccount = user.value && user.value.username !== me.username;
  if (changedAccount) {
    clearUserData();
    error.value = "";
  }
  user.value = { username: me.username, is_admin: me.is_admin };
  libraries.value = me.libraries;
  await loadCollections();
  await loadAdminSetup();
  await restorePendingSave(me.username);
}

async function login() {
  error.value = "";
  busy.value = true;
  try {
    const me = await request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: username.value, password: password.value }),
    });
    password.value = "";
    clearUserData();
    user.value = { username: me.username, is_admin: me.is_admin };
    libraries.value = me.libraries;
    await loadCollections();
    await loadAdminSetup();
    await restorePendingSave(me.username);
  } catch (reason) {
    error.value = reason.message;
  } finally {
    busy.value = false;
  }
}

async function createCollection() {
  const library = libraries.value.find((item) => item.id === adminLibraryId.value);
  if (!user.value?.is_admin || !library || !adminProfileId.value || adminBusy.value) return;

  const limitText = String(initialTrackLimit.value ?? "").trim();
  let maxTracks;
  if (limitText) {
    maxTracks = Number(limitText);
    if (!Number.isInteger(maxTracks) || maxTracks < 1) {
      adminError.value = "Track limit must be a positive whole number, or blank for the full library.";
      return;
    }
  } else if (
    !window.confirm(
      `Ingest the full “${library.name || library.id}” library? This runs synchronously and has no progress or cancel control.`,
    )
  ) {
    return;
  }

  adminError.value = "";
  adminMessage.value = "Ingestion is running. Larger libraries may take several minutes…";
  adminMessageType.value = "info";
  adminBusy.value = true;
  const body = { library_id: library.id, profile: adminProfileId.value };
  if (newCollectionName.value.trim()) body.collection = newCollectionName.value.trim();
  if (maxTracks) body.max_tracks = maxTracks;

  try {
    const result = await request("/api/ingest", { method: "POST", body: JSON.stringify(body) });
    const completion = result.enumeration_complete ? "Library enumeration complete." : "Track limit reached.";
    adminMessage.value = `Collection ${result.collection}: ${result.tracks_processed} processed, ${result.tracks_unchanged} unchanged, ${result.skipped} skipped, ${result.sections_written} sections written. ${completion}`;
    adminMessageType.value = "success";
    newCollectionName.value = "";
    searchResults.value = [];
    hasSearched.value = false;
    try {
      await loadCollections();
      if (collections.value.some((item) => item.name === result.collection)) {
        selectedCollectionName.value = result.collection;
        previousCollectionName.value = result.collection;
      }
    } catch (refreshError) {
      adminMessage.value += ` Ingestion finished, but the collection list could not refresh: ${refreshError.message}`;
      adminMessageType.value = "info";
    }
  } catch (reason) {
    adminError.value = reason.message;
    adminMessage.value = reason.status
      ? "Collection ingestion failed. Review the error; earlier track writes may be retained."
      : "The ingestion result could not be confirmed. It may have completed partially; check the collection list before retrying.";
    adminMessageType.value = "error";
  } finally {
    adminBusy.value = false;
  }
}

async function logout() {
  busy.value = true;
  try {
    await request("/api/auth/logout", { method: "POST" });
    clearUserData();
    error.value = "";
  } catch (reason) {
    error.value = `Could not sign out: ${reason.message}`;
  } finally {
    busy.value = false;
  }
}

function changeCollection() {
  const nextCollection = collections.value.find((item) => item.name === selectedCollectionName.value);
  const oldCollection = collections.value.find((item) => item.name === previousCollectionName.value);
  const switchingLibrary = oldCollection && nextCollection && oldCollection.library_id !== nextCollection.library_id;

  if (switchingLibrary && selectedTracks.value.length) {
    const accepted = window.confirm("Switching libraries clears your selected tracks. Continue?");
    if (!accepted) {
      selectedCollectionName.value = previousCollectionName.value;
      return;
    }
    selectedTracks.value = [];
    selectedLibraryId.value = null;
  }

  previousCollectionName.value = selectedCollectionName.value;
  searchResults.value = [];
  hasSearched.value = false;
  searchError.value = "";
}

async function search() {
  const cleanQuery = query.value.trim();
  if (!cleanQuery || !selectedCollection.value) {
    searchError.value = "Choose a collection and enter a theme or mood.";
    return;
  }

  searchBusy.value = true;
  hasSearched.value = true;
  searchError.value = "";
  try {
    const result = await request("/api/search", {
      method: "POST",
      body: JSON.stringify({ query: cleanQuery, collection: selectedCollection.value.name, limit: 30 }),
    });
    searchResults.value = result.results;
  } catch (reason) {
    searchError.value = reason.message;
    searchResults.value = [];
  } finally {
    searchBusy.value = false;
  }
}

function isSelected(songId) {
  return selectedTracks.value.some((track) => track.song_id === songId);
}

function toggleTrack(track) {
  if (pendingSave.value || !track.song_id || !selectedCollection.value) return;
  const existingIndex = selectedTracks.value.findIndex((item) => item.song_id === track.song_id);
  if (existingIndex >= 0) {
    selectedTracks.value.splice(existingIndex, 1);
    if (!selectedTracks.value.length) selectedLibraryId.value = null;
    return;
  }
  if (selectedTracks.value.length >= 100) {
    saveMessage.value = "A playlist can contain at most 100 tracks.";
    saveMessageType.value = "error";
    return;
  }
  const libraryId = selectedCollection.value.library_id;
  if (selectedLibraryId.value && selectedLibraryId.value !== libraryId) return;
  selectedLibraryId.value = libraryId;
  selectedTracks.value.push({ ...track, library_id: libraryId });
}

function moveTrack(index, direction) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= selectedTracks.value.length) return;
  const reordered = [...selectedTracks.value];
  [reordered[index], reordered[nextIndex]] = [reordered[nextIndex], reordered[index]];
  selectedTracks.value = reordered;
}

function persistPendingSave(operation) {
  try {
    sessionStorage.setItem(pendingSaveKey(operation.owner), JSON.stringify(operation));
    return true;
  } catch {
    saveMessage.value = "Browser storage is unavailable, so no playlist was submitted. Enable session storage and try again.";
    saveMessageType.value = "error";
    return false;
  }
}

function clearStoredPendingSave(owner = user.value?.username) {
  if (!owner) return;
  try {
    sessionStorage.removeItem(pendingSaveKey(owner));
  } catch {
    // The current operation can still be cleared in memory; a later login rechecks any stored operation.
  }
}

function completePendingSave(operation) {
  if (!operation) return;
  clearStoredPendingSave(operation.owner);
  pendingSave.value = null;
  pendingSaveStatus.value = null;
}

function showOperation(operation) {
  pendingSaveStatus.value = operation.status;
  if (operation.status === "verified") {
    const request = pendingSave.value?.request;
    const tracksById = new Map(selectedTracks.value.map((track) => [track.song_id, track]));
    completedSave.value = request
      ? {
          name: request.name,
          playlistId: operation.playlist_id || null,
          tracks: request.song_ids.map((songId) => tracksById.get(songId) || { song_id: songId, title: songId, artist: "" }),
        }
      : null;
    saveMessage.value = `Private playlist saved and verified${operation.playlist_id ? ` (Navidrome ID ${operation.playlist_id})` : ""}.`;
    saveMessageType.value = "success";
    completePendingSave(pendingSave.value);
    selectedTracks.value = [];
    selectedLibraryId.value = null;
    playlistName.value = "";
    allowDuplicateName.value = false;
    return;
  }
  if (operation.status === "failed") {
    saveMessage.value = `Navidrome rejected the playlist save${operation.reason ? ` (${operation.reason})` : ""}. Review your selection and try again.`;
    saveMessageType.value = "error";
    completePendingSave(pendingSave.value);
    return;
  }
  saveMessage.value = `Playlist save status: ${operation.status}.`;
  saveMessageType.value = operation.status === "prepared" ? "info" : "warning";
}

async function checkPendingSave() {
  const operation = pendingSave.value;
  if (!operation || !user.value || operation.owner !== user.value.username) return;
  saveBusy.value = true;
  try {
    const currentUser = await request("/api/auth/me");
    if (currentUser.username !== operation.owner) {
      clearUserData();
      error.value = `Sign in as ${operation.owner} to check this saved playlist operation. The operation remains stored in this browser session.`;
      return;
    }
    const status = await request(
      `/api/navidrome/operations/${encodeURIComponent(operation.operation_id)}?library_id=${encodeURIComponent(operation.request.library_id)}`,
    );
    showOperation(status);
  } catch (reason) {
    if (reason.status === 401) {
      clearUserData();
      error.value = "Your session expired. Sign in again to check the saved playlist operation.";
    } else if (reason.code === "operation_not_found") {
      pendingSaveStatus.value = "operation_not_found";
      saveMessage.value = "No save record exists yet. You can safely retry the exact same playlist request.";
      saveMessageType.value = "info";
    } else if (reason.status !== 401) {
      pendingSaveStatus.value = "status_unavailable";
      saveMessage.value = `Could not check the previous save: ${reason.message}. Do not start another playlist until this operation is checked.`;
      saveMessageType.value = "warning";
    }
  } finally {
    saveBusy.value = false;
  }
}

async function submitPendingSave() {
  const operation = pendingSave.value;
  if (!operation || !user.value || operation.owner !== user.value.username || saveBusy.value) return;
  if (!persistPendingSave(operation)) return;

  saveBusy.value = true;
  saveMessage.value = "Saving and verifying your private playlist…";
  saveMessageType.value = "info";
  try {
    const currentUser = await request("/api/auth/me");
    if (currentUser.username !== operation.owner) {
      clearUserData();
      error.value = `Sign in as ${operation.owner} to submit this saved playlist operation. The operation remains stored in this browser session.`;
      return;
    }
    const result = await request("/api/navidrome/playlists", {
      method: "POST",
      body: JSON.stringify({ operation_id: operation.operation_id, ...operation.request }),
    });
    showOperation(result);
    if (pendingSave.value && result.status !== "verified" && result.status !== "failed") {
      await checkPendingSave();
    }
  } catch (reason) {
    if (reason.code === "duplicate_name") {
      duplicateNameNeedsAcknowledgement.value = true;
      pendingSave.value = null;
      pendingSaveStatus.value = null;
      clearStoredPendingSave(operation.owner);
      saveMessage.value = "That playlist name already exists. Confirm that you want another playlist with the same name.";
      saveMessageType.value = "warning";
    } else if (reason.status === 422 && reason.code === "stale_selection") {
      completePendingSave(operation);
      selectedTracks.value = [];
      selectedLibraryId.value = null;
      searchResults.value = [];
      hasSearched.value = false;
      saveMessage.value = "Some selected songs changed or are no longer available. Search again and review your selection.";
      saveMessageType.value = "error";
    } else if (reason.status === 401) {
      clearUserData();
      error.value = "Your session expired. Sign in again to continue the saved playlist operation.";
    } else {
      saveMessage.value = `Save response was not conclusive: ${reason.message}. Checking the operation record…`;
      saveMessageType.value = "warning";
      await checkPendingSave();
    }
  } finally {
    saveBusy.value = false;
  }
}

function createPendingSave(allowDuplicate = false) {
  if (!user.value || !selectedLibraryId.value || !canSave.value) return;
  const operation = {
    owner: user.value.username,
    operation_id: crypto.randomUUID(),
    request: {
      library_id: selectedLibraryId.value,
      name: playlistName.value.trim(),
      song_ids: selectedTracks.value.map((track) => track.song_id),
      allow_duplicate_name: allowDuplicate,
    },
  };
  completedSave.value = null;
  pendingSave.value = operation;
  pendingSaveStatus.value = "prepared";
  duplicateNameNeedsAcknowledgement.value = false;
  if (!persistPendingSave(operation)) {
    pendingSave.value = null;
    pendingSaveStatus.value = null;
    return;
  }
  submitPendingSave();
}

function savePlaylist() {
  createPendingSave(allowDuplicateName.value);
}

function retryPendingSave() {
  if (!canReplayPendingSave.value) return;
  submitPendingSave();
}

function dismissUnresolvedSave() {
  const accepted = window.confirm(
    "This save was not verified. Dismiss only after checking Navidrome manually; an earlier request may still have created a playlist.",
  );
  if (!accepted) return;
  completePendingSave(pendingSave.value);
  saveMessage.value = "Unresolved save dismissed after manual inspection. No success was assumed.";
  saveMessageType.value = "warning";
}

onMounted(async () => {
  try {
    await refresh();
  } catch {
    user.value = null;
  }
});
</script>

<template>
  <main class="shell">
    <header class="topbar">
      <a class="brand" href="/app/" aria-label="Resonance home"><span class="brand-mark">R</span> resonance</a>
      <span class="eyebrow">PERSONAL MUSIC DISCOVERY</span>
    </header>

    <section v-if="!authenticated" class="login card">
      <p class="eyebrow accent">YOUR LIBRARY, YOUR ACCOUNT</p>
      <h1>Sign in to Resonance</h1>
      <p class="muted">Use your Navidrome account. Resonance only shows music your account can access.</p>
      <form @submit.prevent="login">
        <label>Username<input v-model="username" name="username" autocomplete="username" required /></label>
        <label>Password<input v-model="password" name="password" type="password" autocomplete="current-password" required /></label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="primary" :disabled="busy">{{ busy ? "Signing in…" : "Sign in" }}</button>
      </form>
      <p class="fine">Authentication is handled by your Navidrome server.</p>
    </section>

    <template v-else>
      <section class="welcome">
        <div>
          <p class="eyebrow accent">WELCOME BACK</p>
          <h1>Find songs for the moment</h1>
          <p class="muted">Signed in as <strong>{{ user.username }}</strong><span v-if="user.is_admin" class="badge">Administrator</span></p>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
        </div>
        <button class="quiet" :disabled="busy || saveBusy || adminBusy" @click="logout">Sign out</button>
      </section>

      <section v-if="user.is_admin" class="card admin-card">
        <div class="section-heading">
          <div><p class="eyebrow accent">ADMINISTRATION</p><h2>Create a search collection</h2></div>
          <span class="badge">Administrator</span>
        </div>
        <p class="muted">Index a Navidrome library with an embedding profile. Collection creation and ingestion happen together.</p>
        <form class="admin-form" @submit.prevent="createCollection">
          <label>Navidrome library
            <select v-model="adminLibraryId" :disabled="adminBusy || !libraries.length" required>
              <option disabled value="">Choose a library</option>
              <option v-for="library in libraries" :key="library.id" :value="library.id">
                {{ library.name || library.id }}
              </option>
            </select>
          </label>
          <label>Embedding profile
            <select v-model="adminProfileId" :disabled="adminBusy || !embeddingProfiles.length" required>
              <option disabled value="">Choose an embedding profile</option>
              <option v-for="profile in embeddingProfiles" :key="profile.id" :value="profile.id">
                {{ profile.id }} · {{ profile.model_id }} · {{ profile.dimensions }} dimensions{{ profile.is_default ? " · default" : "" }}
              </option>
            </select>
          </label>
          <p v-if="selectedAdminProfile" class="fine admin-profile-detail">
            {{ selectedAdminProfile.protocol }}<template v-if="selectedAdminProfile.revision"> · revision {{ selectedAdminProfile.revision }}</template>
          </p>
          <label>Collection name <span class="muted">Optional; leave blank to generate a name</span>
            <input v-model="newCollectionName" maxlength="255" autocomplete="off" placeholder="e.g. library-model-experiment" :disabled="adminBusy" />
          </label>
          <label>Initial track limit <span class="muted">Defaults to 10; leave blank to ingest the full library</span>
            <input v-model="initialTrackLimit" type="number" min="1" step="1" placeholder="10" :disabled="adminBusy" />
          </label>
          <p v-if="!libraries.length" class="muted">No Navidrome libraries are available to this account.</p>
          <p v-if="adminError" class="error" role="alert">{{ adminError }}</p>
          <p v-if="adminMessage" class="admin-result" :class="`message-${adminMessageType}`" role="status">{{ adminMessage }}</p>
          <button class="primary search-button" :disabled="adminBusy || !libraries.length || !embeddingProfiles.length">
            {{ adminBusy ? "Indexing…" : "Create collection and ingest" }}
          </button>
        </form>
      </section>

      <section class="card search-card">
        <div class="section-heading">
          <div><p class="eyebrow accent">SEMANTIC SEARCH</p><h2>What do you want to hear?</h2></div>
          <span v-if="selectedLibrary" class="library-pill">{{ selectedLibrary.name || selectedLibrary.id }}</span>
        </div>
        <form @submit.prevent="search">
          <label>Collection
            <select v-model="selectedCollectionName" :disabled="!collections.length || searchBusy || adminBusy || !!pendingSave" required @change="changeCollection">
              <option disabled value="">Choose an indexed collection</option>
              <optgroup v-for="library in libraries" :key="library.id" :label="library.name || library.id">
                <option v-for="collection in collectionsFor(library.id)" :key="collection.name" :value="collection.name">
                  {{ collection.name }} · {{ collection.model || collection.provider || "embedding profile" }}
                </option>
              </optgroup>
            </select>
          </label>
          <label>Describe a mood, theme, or idea
          <textarea v-model="query" rows="3" maxlength="1000" placeholder="Songs for starting over after a difficult year" required :disabled="adminBusy || !!pendingSave"></textarea>
          </label>
          <p v-if="!collections.length" class="muted">There are no indexed collections in your accessible libraries yet.</p>
          <p v-if="searchError" class="error" role="alert">{{ searchError }}</p>
          <button class="primary search-button" :disabled="searchBusy || adminBusy || !selectedCollectionName || !!pendingSave">
            {{ searchBusy ? "Searching…" : "Search songs" }}
          </button>
        </form>
      </section>

      <section v-if="searchResults.length || searchBusy || hasSearched" class="card results-card">
        <div class="section-heading">
          <div><p class="eyebrow accent">SEARCH RESULTS</p><h2>Review the matches</h2></div>
          <span class="count">{{ searchResults.length }}</span>
        </div>
        <p class="muted">Matches are suggestions based on lyric similarity. Review the lyric excerpt and choose the tracks you want.</p>
        <p v-if="searchBusy" class="empty-state">Finding matching songs…</p>
        <p v-else-if="searchError" class="empty-state">Search could not complete. Review the error above and try again.</p>
        <p v-else-if="!searchResults.length" class="empty-state">No matching tracks found. Try a broader theme or a different collection.</p>
        <article v-for="(track, index) in searchResults" :key="track.song_id || `${track.artist}-${track.title}-${index}`" class="result-row">
          <div class="result-topline">
            <label class="track-choice">
              <input type="checkbox" :checked="isSelected(track.song_id)" :disabled="!!pendingSave || !track.song_id || (selectedTracks.length >= 100 && !isSelected(track.song_id))" @change="toggleTrack(track)" />
              <span><strong>{{ track.title }}</strong><span class="artist-line">{{ track.artist }}<template v-if="track.album"> · {{ track.album }}</template></span></span>
            </label>
            <span class="score">{{ track.score.toFixed(3) }}</span>
          </div>
          <div class="evidence-meta">{{ track.section }} · part {{ track.position + 1 }} of {{ track.total_sections }}</div>
          <blockquote>{{ track.lyrics }}</blockquote>
        </article>
      </section>

      <section v-if="selectedTracks.length || pendingSave" class="card playlist-card">
        <div class="section-heading"><div><p class="eyebrow accent">YOUR SELECTION</p><h2>Build a playlist</h2></div><span class="count">{{ selectedTracks.length }}</span></div>
        <p class="muted">Arrange the tracks, name the playlist, then save it to Navidrome.</p>
        <ol v-if="selectedTracks.length" class="selected-list">
          <li v-for="(track, index) in selectedTracks" :key="track.song_id">
            <span class="order-number">{{ index + 1 }}</span>
            <span class="selected-copy"><strong>{{ track.title }}</strong><span>{{ track.artist }}</span></span>
            <div class="row-actions">
              <button class="icon-button" :disabled="index === 0 || saveBusy || pendingSave" :aria-label="`Move ${track.title} up`" @click="moveTrack(index, -1)">↑</button>
              <button class="icon-button" :disabled="index === selectedTracks.length - 1 || saveBusy || pendingSave" :aria-label="`Move ${track.title} down`" @click="moveTrack(index, 1)">↓</button>
              <button class="icon-button remove-button" :disabled="saveBusy || pendingSave" :aria-label="`Remove ${track.title}`" @click="toggleTrack(track)">×</button>
            </div>
          </li>
        </ol>
        <form class="playlist-form" @submit.prevent="savePlaylist">
          <label>Playlist name<input v-model="playlistName" maxlength="200" placeholder="A name you will recognize" required :disabled="!!pendingSave" @input="duplicateNameNeedsAcknowledgement = false" /></label>
          <label class="check-option"><input v-model="allowDuplicateName" type="checkbox" :disabled="!!pendingSave" /> Allow a playlist with a duplicate name</label>
          <p v-if="duplicateNameNeedsAcknowledgement" class="warning" role="alert">The server found an existing playlist with this name. Confirm the duplicate option and save again to create another.</p>
          <button class="primary" :disabled="!canSave">{{ saveBusy ? "Saving…" : "Create private playlist" }}</button>
        </form>

      </section>

      <section v-if="saveMessage" class="card save-message" :class="`message-${saveMessageType}`" role="status">
        <p>{{ saveMessage }}</p>
        <div v-if="completedSave" class="completed-save">
          <strong>{{ completedSave.name }}</strong>
          <span v-if="completedSave.playlistId" class="muted">Navidrome ID {{ completedSave.playlistId }}</span>
          <ol><li v-for="track in completedSave.tracks" :key="track.song_id">{{ track.title }}<template v-if="track.artist"> — {{ track.artist }}</template></li></ol>
        </div>
        <div v-if="pendingSave" class="recovery-actions">
          <button v-if="canReplayPendingSave" class="quiet small-button" :disabled="saveBusy" @click="retryPendingSave">Retry the same save</button>
          <button v-if="needsManualReview" class="quiet small-button" :disabled="saveBusy" @click="checkPendingSave">Check save status</button>
          <button v-if="needsManualReview" class="quiet small-button" :disabled="saveBusy" @click="dismissUnresolvedSave">I checked Navidrome; dismiss</button>
        </div>
      </section>

      <section v-if="!searchResults.length && !selectedTracks.length && !hasSearched && collections.length" class="card library-card">
        <div class="section-heading"><div><p class="eyebrow accent">YOUR LIBRARIES</p><h2>Available to you</h2></div><span class="count">{{ libraries.length }}</span></div>
        <div v-for="library in libraries" :key="library.id" class="library-row">
          <div class="library-icon">♫</div>
          <div class="library-copy"><h3>{{ library.name || library.id }}</h3><p>{{ library.id }}</p></div>
          <span class="muted">{{ collectionsFor(library.id).length }} collections</span>
        </div>
      </section>
      <footer>Resonance is a private discovery layer for your Navidrome library.</footer>
    </template>
  </main>
</template>
