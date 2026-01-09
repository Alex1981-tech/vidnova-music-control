<template>
  <div class="schedule-view">
    <div class="schedule-header">
      <h1 class="text-h5">{{ $t("schedule.title") }}</h1>
      <Button @click="createNew">
        <Plus class="size-4" />
        {{ $t("schedule.new") }}
      </Button>
    </div>

    <Container variant="default" class="mt-4">
      <div v-if="loading" class="loading-state">
        <v-progress-circular indeterminate />
      </div>

      <v-list v-else-if="schedules.length > 0" class="schedule-list">
        <ListItem
          v-for="item in schedules"
          :key="item.schedule_id"
          link
          :show-menu-btn="true"
          @click="editSchedule(item.schedule_id)"
          @menu="(evt) => onMenu(evt, item)"
        >
          <template #prepend>
            <div class="schedule-icon" :class="{ active: item.enabled && item.state === 'playing' }">
              <CalendarClock class="size-10" />
            </div>
          </template>

          <template #title>
            <div class="schedule-name">
              {{ item.name }}
            </div>
          </template>

          <template #subtitle>
            <div class="schedule-meta">
              <span class="schedule-time">
                {{ item.start_time }} - {{ item.end_time }}
              </span>
              <span class="schedule-days">
                {{ formatDays(item.days_of_week) }}
              </span>
              <span v-if="item.state === 'playing'" class="schedule-playing">
                <Play class="size-3" /> {{ $t("state.playing") }}
              </span>
            </div>
          </template>

          <template #append>
            <div class="schedule-status">
              <v-switch
                :model-value="item.enabled"
                hide-details
                density="compact"
                color="primary"
                @update:model-value="toggleEnabled(item)"
                @click.stop
              />
            </div>
          </template>
        </ListItem>
      </v-list>

      <div v-else class="empty-state">
        <CalendarClock class="empty-icon size-16" />
        <div class="empty-title">{{ $t("schedule.no_schedules") }}</div>
        <div class="empty-message">{{ $t("schedule.no_schedules_detail") }}</div>
        <Button class="mt-4" @click="createNew">
          <Plus class="size-4" />
          {{ $t("schedule.new") }}
        </Button>
      </div>
    </Container>
  </div>
</template>

<script setup lang="ts">
import Container from "@/components/Container.vue";
import ListItem from "@/components/ListItem.vue";
import { Button } from "@/components/ui/button";
import { ContextMenuItem } from "@/layouts/default/ItemContextMenu.vue";
import { api } from "@/plugins/api";
import { eventbus } from "@/plugins/eventbus";
import { CalendarClock, Play, Plus } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";

defineOptions({
  name: "ScheduleView",
});

interface Schedule {
  schedule_id: string;
  name: string;
  enabled: boolean;
  start_time: string;
  end_time: string;
  days_of_week: number[];
  media_items: string[];
  players: { player_id: string; volume: number }[];
  group_players: boolean;
  loop_content: boolean;
  shuffle: boolean;
  announcements: any[];
  state: string;
}

const router = useRouter();
const { t } = useI18n();

const schedules = ref<Schedule[]>([]);
const loading = ref(true);

const dayNames = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const formatDays = (days: number[]) => {
  if (days.length === 7) return t("schedule.every_day");
  if (days.length === 5 && days.every((d) => d < 5)) return t("schedule.weekdays");
  if (days.length === 2 && days.includes(5) && days.includes(6)) return t("schedule.weekends");
  return days.map((d) => t(`days.${dayNames[d]}`)).join(", ");
};

const loadSchedules = async () => {
  loading.value = true;
  try {
    schedules.value = await api.sendCommand("schedule/all");
  } catch (e) {
    console.error("Failed to load schedules:", e);
    schedules.value = [];
  }
  loading.value = false;
};

const createNew = () => {
  router.push("/schedule/new");
};

const editSchedule = (scheduleId: string) => {
  router.push(`/schedule/${scheduleId}/edit`);
};

const toggleEnabled = async (schedule: Schedule) => {
  try {
    await api.sendCommand("schedule/enable", {
      schedule_id: schedule.schedule_id,
      enabled: !schedule.enabled,
    });
    schedule.enabled = !schedule.enabled;
  } catch (e) {
    console.error("Failed to toggle schedule:", e);
  }
};

const deleteSchedule = async (schedule: Schedule) => {
  if (!confirm(t("schedule.confirm_delete"))) return;
  try {
    await api.sendCommand("schedule/delete", {
      schedule_id: schedule.schedule_id,
    });
    schedules.value = schedules.value.filter(
      (s) => s.schedule_id !== schedule.schedule_id
    );
  } catch (e) {
    console.error("Failed to delete schedule:", e);
  }
};

const triggerNow = async (schedule: Schedule) => {
  try {
    await api.sendCommand("schedule/trigger", {
      schedule_id: schedule.schedule_id,
    });
    await loadSchedules();
  } catch (e) {
    console.error("Failed to trigger schedule:", e);
  }
};

const stopSchedule = async (schedule: Schedule) => {
  try {
    await api.sendCommand("schedule/stop", {
      schedule_id: schedule.schedule_id,
    });
    await loadSchedules();
  } catch (e) {
    console.error("Failed to stop schedule:", e);
  }
};

const onMenu = (evt: Event, schedule: Schedule) => {
  const menuItems: ContextMenuItem[] = [
    {
      label: "edit",
      labelArgs: [],
      action: () => editSchedule(schedule.schedule_id),
      icon: "mdi-pencil",
    },
    {
      label: schedule.state === "playing" ? "schedule.stop" : "schedule.trigger_now",
      labelArgs: [],
      action: () =>
        schedule.state === "playing"
          ? stopSchedule(schedule)
          : triggerNow(schedule),
      icon: schedule.state === "playing" ? "mdi-stop" : "mdi-play",
    },
    {
      label: schedule.enabled ? "settings.disable" : "settings.enable",
      labelArgs: [],
      action: () => toggleEnabled(schedule),
      icon: schedule.enabled ? "mdi-toggle-switch-off" : "mdi-toggle-switch",
    },
    {
      label: "settings.delete",
      labelArgs: [],
      action: () => deleteSchedule(schedule),
      icon: "mdi-delete",
    },
  ];
  eventbus.emit("contextmenu", {
    items: menuItems,
    posX: (evt as PointerEvent).clientX,
    posY: (evt as PointerEvent).clientY,
  });
};

onMounted(() => {
  loadSchedules();
});
</script>

<style scoped>
.schedule-view {
  padding: 20px;
}

.schedule-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.schedule-list {
  background: transparent;
}

.schedule-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgba(var(--v-theme-primary), 0.7);
  margin-right: 12px;
}

.schedule-icon.active {
  background: rgba(var(--v-theme-success), 0.2);
  color: rgb(var(--v-theme-success));
}

.schedule-name {
  font-weight: 500;
  font-size: 16px;
}

.schedule-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
  flex-wrap: wrap;
}

.schedule-time {
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-weight: 500;
}

.schedule-days {
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.schedule-playing {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: rgb(var(--v-theme-success));
  font-weight: 500;
}

.schedule-status {
  display: flex;
  align-items: center;
}

.loading-state {
  display: flex;
  justify-content: center;
  padding: 60px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.empty-icon {
  color: rgba(var(--v-theme-on-surface), 0.3);
  margin-bottom: 16px;
}

.empty-title {
  font-size: 18px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.7);
  margin-bottom: 8px;
}

.empty-message {
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  line-height: 1.4;
}
</style>
