<template>
  <div class="schedule-edit-view">
    <div class="schedule-edit-header">
      <Button variant="ghost" size="sm" @click="goBack">
        <ArrowLeft class="size-4" />
        {{ $t("back") }}
      </Button>
      <h1 class="text-h6">
        {{ isNew ? $t("schedule.new") : $t("schedule.edit") }}
      </h1>
      <div class="header-actions">
        <Button variant="outline" size="sm" @click="goBack">
          {{ $t("cancel") }}
        </Button>
        <Button size="sm" :disabled="saving" @click="saveSchedule">
          <Save class="size-4" />
          {{ $t("schedule.save") }}
        </Button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <v-progress-circular indeterminate size="24" />
    </div>

    <div v-else class="schedule-form-compact">
      <!-- Row 1: Name and Enable -->
      <div class="form-row">
        <v-text-field
          v-model="form.name"
          :label="$t('schedule.name')"
          :rules="[rules.required]"
          variant="outlined"
          density="compact"
          hide-details
          class="name-field"
        />
        <v-switch
          v-model="form.enabled"
          :label="$t('schedule.enabled')"
          color="primary"
          hide-details
          density="compact"
          class="enable-switch"
        />
      </div>

      <!-- Row 2: Time and Days -->
      <div class="form-row time-days-row">
        <v-text-field
          v-model="form.start_time"
          :label="$t('schedule.start_time')"
          type="time"
          variant="outlined"
          density="compact"
          hide-details
          class="time-field"
        />
        <v-text-field
          v-model="form.end_time"
          :label="$t('schedule.end_time')"
          type="time"
          variant="outlined"
          density="compact"
          hide-details
          class="time-field"
        />
        <div class="days-chips-inline">
          <v-chip
            v-for="(day, index) in dayNames"
            :key="index"
            :color="form.days_of_week.includes(index) ? 'primary' : 'default'"
            :variant="form.days_of_week.includes(index) ? 'flat' : 'outlined'"
            size="small"
            @click="toggleDay(index)"
          >
            {{ $t(`days.${day}_short`) }}
          </v-chip>
        </div>
      </div>

      <!-- Row 3: Players -->
      <div class="form-section-compact">
        <div class="section-header">
          <span class="section-label">{{ $t("schedule.players") }}</span>
          <Button variant="ghost" size="sm" @click="addPlayer">
            <Plus class="size-3" />
          </Button>
        </div>
        <div class="players-grid">
          <div v-for="(playerSetting, index) in form.players" :key="index" class="player-item">
            <v-select
              v-model="playerSetting.player_id"
              :items="availablePlayers"
              item-title="name"
              item-value="player_id"
              variant="outlined"
              density="compact"
              hide-details
              class="player-select-compact"
            />
            <div class="volume-compact">
              <v-icon size="16">mdi-volume-medium</v-icon>
              <input
                v-model.number="playerSetting.volume"
                type="range"
                min="0"
                max="100"
                class="volume-range"
              />
              <span class="volume-value">{{ playerSetting.volume }}%</span>
            </div>
            <Button variant="ghost" size="icon" class="remove-btn" @click="removePlayer(index)">
              <X class="size-3" />
            </Button>
          </div>
        </div>
        <v-checkbox
          v-model="form.group_players"
          :label="$t('schedule.group_players')"
          density="compact"
          hide-details
          class="group-checkbox"
        />
      </div>

      <!-- Row 4: Media/Playlist Selection -->
      <div class="form-section-compact">
        <div class="section-header">
          <span class="section-label">{{ $t("schedule.media") }}</span>
        </div>

        <!-- Playlist selector -->
        <div class="playlist-selector">
          <v-select
            v-model="selectedPlaylist"
            :items="availablePlaylists"
            item-title="name"
            item-value="uri"
            :label="$t('schedule.select_playlist')"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            :loading="loadingPlaylists"
            @update:model-value="onPlaylistSelected"
          >
            <template #item="{ item, props }">
              <v-list-item v-bind="props">
                <template #prepend>
                  <v-avatar size="32" rounded="sm">
                    <v-img v-if="item.raw.image" :src="item.raw.image" />
                    <v-icon v-else>mdi-playlist-music</v-icon>
                  </v-avatar>
                </template>
                <template #subtitle>
                  <span class="text-caption">{{ item.raw.provider }}</span>
                </template>
              </v-list-item>
            </template>
          </v-select>
        </div>

        <!-- Selected media items -->
        <div v-if="form.media_items.length" class="selected-media">
          <div v-for="(uri, index) in form.media_items" :key="index" class="media-chip">
            <span class="media-name">{{ getMediaName(uri) }}</span>
            <Button variant="ghost" size="icon" class="remove-btn-small" @click="removeMedia(index)">
              <X class="size-3" />
            </Button>
          </div>
        </div>

        <!-- Playback options inline -->
        <div class="playback-options-inline">
          <v-checkbox
            v-model="form.loop_content"
            :label="$t('schedule.loop')"
            density="compact"
            hide-details
          />
          <v-checkbox
            v-model="form.shuffle"
            :label="$t('schedule.shuffle')"
            density="compact"
            hide-details
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Button } from "@/components/ui/button";
import { api } from "@/plugins/api";
import { ArrowLeft, Plus, Save, X } from "lucide-vue-next";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";

defineOptions({
  name: "ScheduleEditView",
});

interface PlayerVolumeSetting {
  player_id: string;
  volume: number;
}

interface ScheduleForm {
  schedule_id: string;
  name: string;
  enabled: boolean;
  start_time: string;
  end_time: string;
  days_of_week: number[];
  media_items: string[];
  players: PlayerVolumeSetting[];
  group_players: boolean;
  loop_content: boolean;
  shuffle: boolean;
  announcements: any[];
}

interface PlaylistItem {
  uri: string;
  name: string;
  provider: string;
  image?: string;
}

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const loading = ref(true);
const saving = ref(false);
const loadingPlaylists = ref(false);

const scheduleId = computed(() => route.params.id as string | undefined);
const isNew = computed(() => !scheduleId.value || scheduleId.value === "new");

const dayNames = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const form = reactive<ScheduleForm>({
  schedule_id: "",
  name: "",
  enabled: true,
  start_time: "09:00",
  end_time: "18:00",
  days_of_week: [0, 1, 2, 3, 4],
  media_items: [],
  players: [],
  group_players: false,
  loop_content: true,
  shuffle: false,
  announcements: [],
});

const availablePlayers = ref<{ player_id: string; name: string }[]>([]);
const availablePlaylists = ref<PlaylistItem[]>([]);
const selectedPlaylist = ref<string | null>(null);

const rules = {
  required: (v: string) => !!v || t("settings.invalid_input"),
};

const loadPlayers = async () => {
  try {
    const queues = await api.getPlayerQueues();
    availablePlayers.value = queues.map((q: any) => ({
      player_id: q.queue_id,
      name: q.display_name || q.queue_id,
    }));
  } catch (e) {
    console.error("Failed to load players:", e);
  }
};

const loadPlaylists = async () => {
  loadingPlaylists.value = true;
  try {
    // Load playlists from library
    const libraryPlaylists = await api.getLibraryPlaylists();

    availablePlaylists.value = libraryPlaylists.map((p: any) => ({
      uri: p.uri,
      name: p.name,
      provider: p.provider_mappings?.[0]?.provider_domain || "library",
      image: p.metadata?.images?.[0]?.path || p.image?.path,
    }));
  } catch (e) {
    console.error("Failed to load playlists:", e);
  }
  loadingPlaylists.value = false;
};

const loadSchedule = async () => {
  if (isNew.value) {
    loading.value = false;
    return;
  }

  try {
    const schedule = await api.sendCommand("schedule/get", {
      schedule_id: scheduleId.value,
    });
    Object.assign(form, schedule);
    // Set selected playlist if media_items has one
    if (form.media_items.length > 0) {
      selectedPlaylist.value = form.media_items[0];
    }
  } catch (e) {
    console.error("Failed to load schedule:", e);
    router.push("/schedule");
  }
  loading.value = false;
};

const toggleDay = (dayIndex: number) => {
  const index = form.days_of_week.indexOf(dayIndex);
  if (index >= 0) {
    form.days_of_week.splice(index, 1);
  } else {
    form.days_of_week.push(dayIndex);
    form.days_of_week.sort();
  }
};

const addPlayer = () => {
  form.players.push({ player_id: "", volume: 50 });
};

const removePlayer = (index: number) => {
  form.players.splice(index, 1);
};

const onPlaylistSelected = (uri: string | null) => {
  if (uri && !form.media_items.includes(uri)) {
    form.media_items.push(uri);
  }
  // Reset selector after adding
  setTimeout(() => {
    selectedPlaylist.value = null;
  }, 100);
};

const removeMedia = (index: number) => {
  form.media_items.splice(index, 1);
};

const getMediaName = (uri: string): string => {
  const playlist = availablePlaylists.value.find(p => p.uri === uri);
  if (playlist) return playlist.name;
  // Extract name from URI
  const parts = uri.split("/");
  return parts[parts.length - 1] || uri;
};

const saveSchedule = async () => {
  if (!form.name) {
    alert(t("schedule.name_required"));
    return;
  }

  saving.value = true;
  try {
    const data = { ...form };
    // Filter out empty values
    data.media_items = data.media_items.filter((m) => m.trim());
    data.players = data.players.filter((p) => p.player_id);

    if (isNew.value) {
      await api.sendCommand("schedule/create", data);
    } else {
      await api.sendCommand("schedule/update", data);
    }
    router.push("/schedule");
  } catch (e) {
    console.error("Failed to save schedule:", e);
    alert(t("schedule.save_failed"));
  }
  saving.value = false;
};

const goBack = () => {
  router.push("/schedule");
};

onMounted(async () => {
  await Promise.all([loadPlayers(), loadPlaylists()]);
  await loadSchedule();
});

watch(
  () => route.params.id,
  () => {
    loading.value = true;
    loadSchedule();
  }
);
</script>

<style scoped>
.schedule-edit-view {
  padding: 12px 16px;
  max-width: 900px;
  margin: 0 auto;
}

.schedule-edit-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.schedule-edit-header h1 {
  flex: 1;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.loading-state {
  display: flex;
  justify-content: center;
  padding: 40px;
}

.schedule-form-compact {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.name-field {
  flex: 1;
}

.enable-switch {
  flex-shrink: 0;
}

.time-days-row {
  flex-wrap: wrap;
}

.time-field {
  width: 120px;
  flex-shrink: 0;
}

.days-chips-inline {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  flex: 1;
}

.form-section-compact {
  background: rgba(var(--v-theme-surface-variant), 0.15);
  border-radius: 8px;
  padding: 12px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-label {
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.7);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.players-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.player-item {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(var(--v-theme-surface), 0.5);
  padding: 6px 8px;
  border-radius: 6px;
}

.player-select-compact {
  width: 180px;
  flex-shrink: 0;
}

.volume-compact {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}

.volume-range {
  flex: 1;
  height: 4px;
  cursor: pointer;
}

.volume-value {
  font-size: 12px;
  width: 36px;
  text-align: right;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.remove-btn {
  width: 24px;
  height: 24px;
  padding: 0;
}

.group-checkbox {
  margin-top: 8px;
}

.playlist-selector {
  margin-bottom: 8px;
}

.selected-media {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.media-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(var(--v-theme-primary), 0.15);
  color: rgb(var(--v-theme-primary));
  padding: 4px 8px 4px 12px;
  border-radius: 16px;
  font-size: 13px;
}

.media-name {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-btn-small {
  width: 20px;
  height: 20px;
  padding: 0;
  min-width: 20px;
}

.playback-options-inline {
  display: flex;
  gap: 16px;
}

@media (max-width: 600px) {
  .form-row {
    flex-direction: column;
    align-items: stretch;
  }

  .time-field {
    width: 100%;
  }

  .player-select-compact {
    width: 100%;
  }

  .player-item {
    flex-wrap: wrap;
  }
}
</style>
