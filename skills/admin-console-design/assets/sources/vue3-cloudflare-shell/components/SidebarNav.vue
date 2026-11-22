<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import Icon from "./Icon.vue";

const props = withDefaults(
  defineProps<{
    expanded: boolean;
    showToggle?: boolean;
  }>(),
  { showToggle: true },
);

const emit = defineEmits<{
  navigate: [];
  toggle: [];
}>();

const route = useRoute();

const batchesActive = computed(
  () => route.path.startsWith("/batches") && route.path !== "/batches/new",
);
const newBatchActive = computed(() => route.path === "/batches/new");
const consoleActive = computed(() => false);

function rowLabel(label: string) {
  return props.expanded ? undefined : label;
}
</script>

<template>
  <div class="sidebar-nav">
    <nav class="sidebar-scroll" aria-label="主导航">
      <div class="nav-section">
        <div v-if="expanded" class="nav-section-label">工作台</div>
        <ul class="nav-list">
          <li>
            <RouterLink
              to="/batches"
              class="nav-row"
              :class="{ active: batchesActive }"
              :aria-current="batchesActive ? 'page' : undefined"
              :aria-label="rowLabel('采集批次')"
              :title="expanded ? undefined : '采集批次'"
              @click="emit('navigate')"
            >
              <span class="nav-icon"><Icon name="layers" /></span>
              <span class="nav-label">采集批次</span>
              <span v-if="batchesActive" class="nav-active-bar" aria-hidden="true"></span>
            </RouterLink>
          </li>
          <li>
            <RouterLink
              to="/batches/new"
              class="nav-row"
              :class="{ active: newBatchActive }"
              :aria-current="newBatchActive ? 'page' : undefined"
              :aria-label="rowLabel('新建批次')"
              :title="expanded ? undefined : '新建批次'"
              @click="emit('navigate')"
            >
              <span class="nav-icon"><Icon name="plus" /></span>
              <span class="nav-label">新建批次</span>
              <span v-if="newBatchActive" class="nav-active-bar" aria-hidden="true"></span>
            </RouterLink>
          </li>
        </ul>
      </div>

      <div class="nav-divider" aria-hidden="true"></div>

      <div class="nav-section">
        <div v-if="expanded" class="nav-section-label">系统</div>
        <ul class="nav-list">
          <li>
            <a
              href="/"
              class="nav-row"
              :class="{ active: consoleActive }"
              :aria-label="rowLabel('内部任务控制台')"
              :title="expanded ? undefined : '内部任务控制台'"
            >
              <span class="nav-icon"><Icon name="terminal" /></span>
              <span class="nav-label">内部任务控制台</span>
              <span class="nav-trailing"><Icon name="external" /></span>
            </a>
          </li>
        </ul>
      </div>
    </nav>

    <div v-if="showToggle" class="sidebar-footer">
      <button
        type="button"
        class="nav-row sidebar-toggle"
        :aria-expanded="expanded"
        aria-controls="app-sidebar"
        :aria-label="expanded ? '收起侧边栏' : '展开侧边栏'"
        :title="expanded ? '收起侧边栏' : '展开侧边栏'"
        @click="emit('toggle')"
      >
        <span class="nav-icon">
          <Icon :name="expanded ? 'panel-close' : 'panel-open'" />
        </span>
        <span class="nav-label">{{ expanded ? "收起侧边栏" : "展开侧边栏" }}</span>
      </button>
    </div>
  </div>
</template>
