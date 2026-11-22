<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import Icon from "./components/Icon.vue";
import SidebarNav from "./components/SidebarNav.vue";

interface Health {
  status?: string;
  version?: string;
  worker?: string | null;
}

const HEALTH_URL = "/api/health";
const HEALTH_POLL_MS = 30_000;
const SIDEBAR_KEY = "admin.sidebar.pinned";
const DESKTOP_QUERY = "(min-width: 1024px)";

const route = useRoute();
const health = ref<Health | null>(null);
const healthError = ref("");
const pinned = ref(readPinned());
const peek = ref(false);
const drawerOpen = ref(false);
const isDesktop = ref(window.innerWidth >= 1024);
const panelRef = ref<HTMLElement | null>(null);
const drawerRef = ref<HTMLElement | null>(null);
const drawerCloseRef = ref<HTMLButtonElement | null>(null);
const menuButtonRef = ref<HTMLButtonElement | null>(null);

let closeTimer: ReturnType<typeof setTimeout> | undefined;
let healthTimer: ReturnType<typeof setInterval> | undefined;
let mediaQuery: MediaQueryList | undefined;
let suppressHover = false;

const expanded = computed(() => (isDesktop.value ? pinned.value || peek.value : true));
const slotWidth = computed(() => {
  if (!isDesktop.value) return 0;
  return pinned.value ? 264 : 56;
});
const panelWidth = computed(() => (expanded.value ? 264 : 56));

const crumbs = computed(() => {
  if (route.path === "/batches") return [{ label: "采集批次", to: null }];
  if (route.path === "/batches/new") {
    return [
      { label: "采集批次", to: "/batches" },
      { label: "新建批次", to: null },
    ];
  }
  if (route.path.includes("/sites/")) {
    return [
      { label: "采集批次", to: "/batches" },
      { label: "批次详情", to: `/batches/${String(route.params.id)}` },
      { label: "站点详情", to: null },
    ];
  }
  return [
    { label: "采集批次", to: "/batches" },
    { label: "批次详情", to: null },
  ];
});

const serviceTone = computed(() => {
  if (healthError.value) return "danger";
  return health.value ? "success" : "muted";
});
const serviceText = computed(() => {
  if (healthError.value) return "服务状态未知";
  if (!health.value) return "读取服务状态";
  return health.value.worker === "managed"
    ? "服务正常 · 托管 worker"
    : "服务正常 · 外部 worker";
});
const serviceShort = computed(() => {
  if (healthError.value) return "异常";
  if (!health.value) return "读取中";
  return "正常";
});
const serviceTitle = computed(() => {
  if (healthError.value) return healthError.value;
  if (!health.value) return "正在读取 /api/health";
  return `版本 ${health.value.version} · worker ${health.value.worker}`;
});

function readPinned(): boolean {
  try {
    const stored = localStorage.getItem(SIDEBAR_KEY);
    if (stored !== null) return stored === "true";
  } catch {
    // private mode or storage disabled: fall back to the viewport default
  }
  return window.innerWidth >= 1280;
}

function persistPinned() {
  try {
    localStorage.setItem(SIDEBAR_KEY, String(pinned.value));
  } catch {
    // persistence is a preference, not a functional requirement
  }
}

async function loadHealth() {
  try {
    const response = await fetch(HEALTH_URL, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    health.value = (await response.json()) as Health;
    healthError.value = "";
  } catch (exc) {
    healthError.value = exc instanceof Error ? exc.message : String(exc);
  }
}

function clearCloseTimer() {
  if (closeTimer !== undefined) {
    clearTimeout(closeTimer);
    closeTimer = undefined;
  }
}

function schedulePeekClose(delay = 220) {
  if (!isDesktop.value || pinned.value) return;
  clearCloseTimer();
  closeTimer = setTimeout(() => {
    peek.value = false;
    closeTimer = undefined;
  }, delay);
}

function onSidebarEnter() {
  if (!isDesktop.value || pinned.value || suppressHover) return;
  clearCloseTimer();
  peek.value = true;
}

function onSidebarLeave() {
  suppressHover = false;
  if (!isDesktop.value || pinned.value) return;
  schedulePeekClose();
}

function onSidebarFocusIn() {
  if (!isDesktop.value || pinned.value) return;
  clearCloseTimer();
  peek.value = true;
}

function onSidebarFocusOut(event: FocusEvent) {
  if (!isDesktop.value || pinned.value) return;
  const next = event.relatedTarget as Node | null;
  if (next && panelRef.value?.contains(next)) return;
  schedulePeekClose(120);
}

function closePeek(moveFocus = false) {
  clearCloseTimer();
  peek.value = false;
  if (moveFocus) {
    void nextTick(() => {
      document.getElementById("main")?.focus();
    });
  }
}

function togglePinned() {
  pinned.value = !pinned.value;
  peek.value = false;
  suppressHover =
    !pinned.value && Boolean(panelRef.value?.matches(":hover"));
  persistPinned();
}

function openDrawer() {
  drawerOpen.value = true;
  void nextTick(() => {
    drawerCloseRef.value?.focus();
  });
}

function closeDrawer(returnFocus = true) {
  if (!drawerOpen.value) return;
  drawerOpen.value = false;
  if (returnFocus) {
    void nextTick(() => menuButtonRef.value?.focus());
  }
}

function trapDrawerFocus(event: KeyboardEvent) {
  if (event.key !== "Tab" || !drawerRef.value) return;
  const nodes = Array.from(
    drawerRef.value.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  );
  if (!nodes.length) return;
  const first = nodes[0];
  const last = nodes[nodes.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  if (drawerOpen.value) {
    event.preventDefault();
    closeDrawer(true);
    return;
  }
  if (peek.value) {
    event.preventDefault();
    closePeek(true);
  }
}

function onMediaChange(event: MediaQueryListEvent) {
  isDesktop.value = event.matches;
  if (!event.matches) {
    drawerOpen.value = false;
    peek.value = false;
  }
}

watch(drawerOpen, (open) => {
  document.body.style.overflow = open ? "hidden" : "";
});

watch(
  () => route.fullPath,
  () => {
    if (drawerOpen.value) closeDrawer(false);
  },
);

onMounted(() => {
  mediaQuery = window.matchMedia(DESKTOP_QUERY);
  isDesktop.value = mediaQuery.matches;
  mediaQuery.addEventListener("change", onMediaChange);
  document.addEventListener("keydown", onKeydown);
  void loadHealth();
  healthTimer = setInterval(loadHealth, HEALTH_POLL_MS);
});

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener("change", onMediaChange);
  document.removeEventListener("keydown", onKeydown);
  if (healthTimer !== undefined) clearInterval(healthTimer);
  clearCloseTimer();
  document.body.style.overflow = "";
});
</script>

<template>
  <a class="skip-link" href="#main">跳到主要内容</a>
  <div class="app-frame">
    <header class="app-topbar">
      <button
        v-if="!isDesktop"
        ref="menuButtonRef"
        type="button"
        class="icon-button"
        aria-label="打开导航"
        aria-controls="mobile-nav"
        :aria-expanded="drawerOpen"
        @click="openDrawer"
      >
        <Icon name="menu" />
      </button>

      <RouterLink class="brand" to="/batches" aria-label="电商采集首页">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M5 8h14M5 12h14M5 16h9" />
          </svg>
        </span>
        <span class="brand-word">电商采集</span>
      </RouterLink>

      <span class="topbar-divider" aria-hidden="true"></span>

      <nav class="breadcrumbs" aria-label="面包屑">
        <template v-for="(crumb, index) in crumbs" :key="crumb.label">
          <RouterLink v-if="crumb.to" :to="crumb.to">{{ crumb.label }}</RouterLink>
          <span v-else class="crumb-current" aria-current="page">{{ crumb.label }}</span>
          <span v-if="index < crumbs.length - 1" class="crumb-sep" aria-hidden="true">
            /
          </span>
        </template>
      </nav>

      <div class="topbar-right">
        <span
          class="service-pill"
          :class="serviceTone"
          :title="serviceTitle"
          role="status"
        >
          <span class="dot" aria-hidden="true"></span>
          <span class="service-text">{{ serviceText }}</span>
          <span class="service-text-short">{{ serviceShort }}</span>
        </span>
      </div>
    </header>

    <div class="app-body">
      <aside
        v-if="isDesktop"
        class="sidebar-slot"
        :style="{ width: `${slotWidth}px` }"
        aria-label="侧边栏"
      >
        <div
          id="app-sidebar"
          ref="panelRef"
          class="sidebar-panel"
          :class="{ 'is-expanded': expanded, 'is-peek': peek }"
          :style="{ width: `${panelWidth}px` }"
          @mouseenter="onSidebarEnter"
          @mouseleave="onSidebarLeave"
          @focusin="onSidebarFocusIn"
          @focusout="onSidebarFocusOut"
        >
          <SidebarNav :expanded="expanded" @toggle="togglePinned" />
        </div>
      </aside>

      <main
        id="main"
        class="app-main"
        :class="{ 'is-peeking': peek }"
        tabindex="-1"
        :aria-hidden="drawerOpen ? 'true' : undefined"
      >
        <div class="content">
          <RouterView />
        </div>
      </main>
    </div>
  </div>

  <Teleport to="body">
    <div v-if="drawerOpen" class="drawer-layer" @keydown="trapDrawerFocus">
      <div class="drawer-overlay" aria-hidden="true" @click="closeDrawer(true)"></div>
      <div
        id="mobile-nav"
        ref="drawerRef"
        class="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-label="导航"
      >
        <div class="drawer-head">
          <span>导航</span>
          <button
            ref="drawerCloseRef"
            type="button"
            class="icon-button"
            aria-label="关闭导航"
            @click="closeDrawer(true)"
          >
            <Icon name="close" />
          </button>
        </div>
        <SidebarNav
          :expanded="true"
          :show-toggle="false"
          @navigate="closeDrawer(true)"
        />
      </div>
    </div>
  </Teleport>
</template>
