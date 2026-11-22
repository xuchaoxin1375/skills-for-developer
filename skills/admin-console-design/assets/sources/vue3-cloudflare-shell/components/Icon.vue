<script setup lang="ts">
defineProps<{
  name:
    | "layers"
    | "plus"
    | "terminal"
    | "panel-close"
    | "panel-open"
    | "menu"
    | "close"
    | "chevron-down"
    | "external";
}>();
</script>

<template>
  <svg
    class="icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <template v-if="name === 'layers'">
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 12 9 5 9-5" />
      <path d="m3 17 9 5 9-5" />
    </template>
    <template v-else-if="name === 'plus'">
      <path d="M12 5v14M5 12h14" />
    </template>
    <template v-else-if="name === 'terminal'">
      <path d="m4 17 6-6-6-6" />
      <path d="M12 19h8" />
    </template>
    <template v-else-if="name === 'panel-close'">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
      <path d="m15 9-3 3 3 3" />
    </template>
    <template v-else-if="name === 'panel-open'">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
      <path d="m13 9 3 3-3 3" />
    </template>
    <template v-else-if="name === 'menu'">
      <path d="M4 6h16M4 12h16M4 18h16" />
    </template>
    <template v-else-if="name === 'close'">
      <path d="m6 6 12 12M18 6 6 18" />
    </template>
    <template v-else-if="name === 'chevron-down'">
      <path d="m6 9 6 6 6-6" />
    </template>
    <template v-else-if="name === 'external'">
      <path d="M14 4h6v6" />
      <path d="m20 4-9 9" />
      <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </template>
  </svg>
</template>
