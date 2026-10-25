<script setup>
import { computed, onMounted, ref } from "vue";

const user = ref(null);
const libraries = ref([]);
const collections = ref([]);
const username = ref("");
const password = ref("");
const error = ref("");
const busy = ref(false);
const authenticated = computed(() => user.value !== null);
const collectionsFor = (libraryId) => collections.value.filter((collection) => collection.library_id === libraryId);

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
      user.value = null;
      error.value = "Your session expired. Sign in again.";
    }
    throw new Error(data?.detail || `Request failed (${response.status})`);
  }
  return data;
}

async function refresh() {
  const me = await request("/api/auth/me");
  user.value = { username: me.username, is_admin: me.is_admin };
  libraries.value = me.libraries;
  collections.value = await request("/api/collections");
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
    user.value = { username: me.username, is_admin: me.is_admin };
    libraries.value = me.libraries;
    collections.value = await request("/api/collections");
  } catch (reason) {
    error.value = reason.message;
  } finally {
    busy.value = false;
  }
}

async function logout() {
  busy.value = true;
  try {
    await request("/api/auth/logout", { method: "POST" });
    user.value = null;
    libraries.value = [];
    collections.value = [];
    error.value = "";
  } catch (reason) {
    error.value = `Could not sign out: ${reason.message}`;
  } finally {
    busy.value = false;
  }
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
          <h1>Your Resonance library</h1>
          <p class="muted">Signed in as <strong>{{ user.username }}</strong><span v-if="user.is_admin" class="badge">Administrator</span></p>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
        </div>
        <button class="quiet" :disabled="busy" @click="logout">Sign out</button>
      </section>

      <section class="card">
        <div class="section-heading"><div><p class="eyebrow accent">AVAILABLE TO YOU</p><h2>Libraries</h2></div><span class="count">{{ libraries.length }}</span></div>
        <p v-if="!libraries.length" class="muted">No Navidrome libraries are available for this account.</p>
        <div v-for="library in libraries" :key="library.id" class="library-row">
          <div class="library-icon">♫</div>
          <div class="library-copy"><h3>{{ library.name || library.id }}</h3><p>{{ library.id }}</p></div>
          <span class="muted">{{ collectionsFor(library.id).length }} collections</span>
        </div>
      </section>

      <section class="card">
        <div class="section-heading"><div><p class="eyebrow accent">SEMANTIC INDEXES</p><h2>Collections</h2></div><span class="count">{{ collections.length }}</span></div>
        <p v-if="!collections.length" class="muted">There are no indexed collections in your accessible libraries yet.</p>
        <template v-for="library in libraries" :key="`group-${library.id}`">
          <div v-if="collectionsFor(library.id).length" class="collection-group">
            <h3>{{ library.name || library.id }}</h3>
            <div v-for="collection in collectionsFor(library.id)" :key="collection.name" class="collection-row">
              <span class="collection-dot"></span>
              <div class="collection-copy"><strong>{{ collection.name }}</strong><span>{{ collection.model || collection.provider || "Embedding profile" }} · {{ collection.points_count }} indexed points</span></div>
            </div>
          </div>
        </template>
      </section>
      <footer>Resonance is a private discovery layer for your Navidrome library.</footer>
    </template>
  </main>
</template>
