<template>
  <section>
    <!-- Header with breadcrumbs and actions -->
    <v-toolbar color="transparent" class="header">
      <template #prepend>
        <v-btn size="small" style="opacity: 0.8" disabled>
          <Folder class="w-6 h-6" />
        </v-btn>
      </template>

      <template #title>
        <div class="breadcrumb-container">
          <span
            v-for="(segment, index) in breadcrumbSegments"
            :key="index"
            class="breadcrumb-segment"
          >
            <button
              v-if="segment.clickable"
              class="breadcrumb-link"
              @click="navigateToSegment(segment.path)"
            >
              {{ segment.text }}
            </button>
            <span v-else class="breadcrumb-text">
              {{ segment.text }}
            </span>
            <v-icon
              v-if="index < breadcrumbSegments.length - 1"
              icon="mdi-chevron-right"
              size="small"
              class="breadcrumb-separator"
            />
          </span>
        </div>
      </template>

      <template #append>
        <!-- View toggle -->
        <v-btn-toggle v-model="viewMode" mandatory density="compact" class="mr-2">
          <v-btn value="list" size="small" icon="mdi-view-list" :title="$t('video_files.view_list')" />
          <v-btn value="grid" size="small" icon="mdi-view-grid" :title="$t('video_files.view_grid')" />
        </v-btn-toggle>

        <!-- Action buttons -->
        <v-btn
          icon="mdi-folder-plus"
          size="small"
          variant="text"
          :title="$t('video_files.create_folder')"
          @click="showCreateFolderDialog = true"
        />
        <v-btn
          icon="mdi-file-upload"
          size="small"
          variant="text"
          :title="$t('video_files.upload')"
          @click="triggerFileUpload"
        />
        <v-btn
          icon="mdi-folder-upload"
          size="small"
          variant="text"
          :title="$t('video_files.upload_folder')"
          @click="triggerFolderUpload"
        />
        <v-btn
          icon="mdi-refresh"
          size="small"
          variant="text"
          :title="$t('refresh')"
          @click="loadItems"
        />
      </template>
    </v-toolbar>

    <!-- Loading state -->
    <v-progress-linear v-if="loading" indeterminate color="primary" />

    <!-- Empty state -->
    <v-container v-if="!loading && items.length === 0" class="text-center py-8">
      <v-icon icon="mdi-folder-open-outline" size="64" color="grey" />
      <p class="text-grey mt-4">{{ $t("video_files.empty") }}</p>
      <v-btn color="primary" variant="outlined" class="mt-4" @click="triggerFileUpload">
        <v-icon icon="mdi-upload" start />
        {{ $t("video_files.upload_first") }}
      </v-btn>
    </v-container>

    <!-- Files and folders - List view -->
    <v-list v-else-if="viewMode === 'list'" lines="two" density="compact">
      <v-list-item
        v-for="item in items"
        :key="item.id"
        :title="item.name"
        :subtitle="getSubtitle(item)"
        @click="handleItemClick(item)"
      >
        <template #prepend>
          <v-icon
            :icon="item.is_folder ? 'mdi-folder' : 'mdi-video'"
            :color="item.is_folder ? 'amber' : 'blue'"
            size="32"
          />
        </template>
        <template #append>
          <template v-if="item.id !== '..'">
            <v-btn
              v-if="!item.is_folder"
              icon="mdi-play-circle"
              size="small"
              variant="text"
              color="success"
              :title="$t('video_files.play')"
              @click.stop="playVideo(item)"
            />
            <v-btn
              icon="mdi-folder-move"
              size="small"
              variant="text"
              color="primary"
              :title="$t('video_files.move')"
              @click.stop="openMoveDialog(item)"
            />
            <v-btn
              icon="mdi-delete"
              size="small"
              variant="text"
              color="error"
              :title="$t('delete')"
              @click.stop="confirmDelete(item)"
            />
          </template>
        </template>
      </v-list-item>
    </v-list>

    <!-- Files and folders - Grid view -->
    <v-container v-else fluid class="pa-2">
      <v-row>
        <v-col
          v-for="item in items"
          :key="item.id"
          cols="6"
          sm="4"
          md="3"
          lg="2"
        >
          <v-card
            class="video-card"
            :class="{ 'folder-card': item.is_folder }"
            @click="handleItemClick(item)"
          >
            <!-- Video thumbnail or folder icon -->
            <div class="card-thumbnail">
              <v-icon
                v-if="item.is_folder"
                icon="mdi-folder"
                color="amber"
                size="64"
              />
              <template v-else>
                <img
                  v-if="item.thumbnail"
                  :src="getThumbnailUrl(item)"
                  class="thumbnail-img"
                  @error="($event.target as HTMLImageElement).style.display = 'none'"
                />
                <v-icon
                  v-else
                  icon="mdi-video"
                  color="blue"
                  size="48"
                  class="video-icon"
                />
                <v-btn
                  icon="mdi-play-circle"
                  size="large"
                  variant="text"
                  color="white"
                  class="play-overlay"
                  @click.stop="playVideo(item)"
                />
              </template>
            </div>

            <v-card-text class="pa-2">
              <div class="text-subtitle-2 text-truncate" :title="item.name">
                {{ item.name }}
              </div>
              <div class="text-caption text-grey">
                {{ getSubtitle(item) }}
              </div>
            </v-card-text>

            <v-card-actions v-if="item.id !== '..'" class="pa-1">
              <v-spacer />
              <v-btn
                icon="mdi-folder-move"
                size="x-small"
                variant="text"
                :title="$t('video_files.move')"
                @click.stop="openMoveDialog(item)"
              />
              <v-btn
                icon="mdi-delete"
                size="x-small"
                variant="text"
                color="error"
                :title="$t('delete')"
                @click.stop="confirmDelete(item)"
              />
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
    </v-container>

    <!-- Hidden file input -->
    <input
      ref="fileInput"
      type="file"
      multiple
      accept="video/*,.mp4,.mkv,.avi,.mov,.webm,.wmv,.flv"
      style="display: none"
      @change="handleFileSelect"
    />

    <!-- Hidden folder input -->
    <input
      ref="folderInput"
      type="file"
      multiple
      webkitdirectory
      style="display: none"
      @change="handleFileSelect"
    />

    <!-- Create folder dialog -->
    <v-dialog v-model="showCreateFolderDialog" max-width="400">
      <v-card>
        <v-card-title>{{ $t("video_files.create_folder") }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="newFolderName"
            :label="$t('video_files.folder_name')"
            variant="outlined"
            density="compact"
            autofocus
            @keyup.enter="createFolder"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showCreateFolderDialog = false">
            {{ $t("cancel") }}
          </v-btn>
          <v-btn color="primary" variant="flat" @click="createFolder" :loading="creating">
            {{ $t("create") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirmation dialog -->
    <v-dialog v-model="showDeleteDialog" max-width="400">
      <v-card>
        <v-card-title>{{ $t("video_files.delete_confirm") }}</v-card-title>
        <v-card-text>
          {{ $t("video_files.delete_message", { name: itemToDelete?.name }) }}
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showDeleteDialog = false">
            {{ $t("cancel") }}
          </v-btn>
          <v-btn color="error" variant="flat" @click="deleteItem" :loading="deleting">
            {{ $t("delete") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Move dialog -->
    <v-dialog v-model="showMoveDialog" max-width="400">
      <v-card>
        <v-card-title>{{ $t("video_files.move_to") }}</v-card-title>
        <v-card-text>
          <p class="mb-3">{{ itemToMove?.name }}</p>
          <v-select
            v-model="selectedDestFolder"
            :items="availableFolders"
            item-title="name"
            item-value="path"
            :label="$t('video_files.destination')"
            variant="outlined"
            density="compact"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showMoveDialog = false">
            {{ $t("cancel") }}
          </v-btn>
          <v-btn color="primary" variant="flat" @click="moveItem" :loading="moving">
            {{ $t("video_files.move") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Upload progress dialog -->
    <v-dialog v-model="showUploadDialog" max-width="400" persistent>
      <v-card>
        <v-card-title>{{ $t("video_files.uploading") }}</v-card-title>
        <v-card-text>
          <p class="mb-2">{{ uploadingFileName }}</p>
          <v-progress-linear
            :model-value="uploadProgress"
            color="primary"
            height="8"
            rounded
          />
          <p class="text-caption text-center mt-2">
            {{ uploadedCount }} / {{ totalFilesToUpload }}
          </p>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Video player dialog -->
    <v-dialog v-model="showPlayerDialog" max-width="900" @after-leave="onPlayerClose">
      <v-card class="video-player-card">
        <v-card-title class="d-flex align-center">
          <span class="text-truncate">{{ currentVideo?.name }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showPlayerDialog = false" />
        </v-card-title>
        <v-card-text class="pa-0">
          <video
            ref="videoPlayer"
            :src="videoStreamUrl"
            controls
            autoplay
            class="video-element"
            @error="onVideoError"
          >
            {{ $t("video_files.not_supported") }}
          </video>
        </v-card-text>
      </v-card>
    </v-dialog>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/plugins/api";
import { useI18n } from "vue-i18n";
import { Folder } from "lucide-vue-next";

interface MediaFileItem {
  id: string;
  name: string;
  path: string;
  is_folder: boolean;
  media_type: string;
  size: number;
  uri: string;
  children_count?: number;
  thumbnail?: string;
}

interface FolderOption {
  name: string;
  path: string;
}

interface BreadcrumbSegment {
  text: string;
  path: string | null;
  clickable: boolean;
}

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

// State
const loading = ref(false);
const items = ref<MediaFileItem[]>([]);
const currentPath = ref("");
const viewMode = ref<"list" | "grid">("list");

// Video player
const showPlayerDialog = ref(false);
const currentVideo = ref<MediaFileItem | null>(null);
const videoPlayer = ref<HTMLVideoElement | null>(null);
const videoStreamUrl = computed(() => {
  if (!currentVideo.value) return "";
  const baseUrl = api.baseUrl || window.location.origin;
  return `${baseUrl}/video/stream?path=${encodeURIComponent(currentVideo.value.path)}`;
});

const getThumbnailUrl = (item: MediaFileItem): string | undefined => {
  if (!item.thumbnail) return undefined;
  const baseUrl = api.baseUrl || window.location.origin;
  return `${baseUrl}/video/thumbnail?name=${encodeURIComponent(item.thumbnail)}`;
};

// Create folder
const showCreateFolderDialog = ref(false);
const newFolderName = ref("");
const creating = ref(false);

// Delete
const showDeleteDialog = ref(false);
const itemToDelete = ref<MediaFileItem | null>(null);
const deleting = ref(false);

// Move
const showMoveDialog = ref(false);
const itemToMove = ref<MediaFileItem | null>(null);
const selectedDestFolder = ref("");
const availableFolders = ref<FolderOption[]>([]);
const moving = ref(false);

// Upload
const fileInput = ref<HTMLInputElement | null>(null);
const folderInput = ref<HTMLInputElement | null>(null);
const showUploadDialog = ref(false);
const uploadProgress = ref(0);
const uploadingFileName = ref("");
const uploadedCount = ref(0);
const totalFilesToUpload = ref(0);

// Breadcrumbs
const breadcrumbSegments = computed((): BreadcrumbSegment[] => {
  const segments: BreadcrumbSegment[] = [];

  // First segment: Browse
  segments.push({
    text: t("browse"),
    path: "__browse__",
    clickable: true,
  });

  // Second segment: Video Assistant
  segments.push({
    text: "Video Assistant",
    path: null,
    clickable: currentPath.value !== "",
  });

  // Path segments
  if (currentPath.value) {
    const parts = currentPath.value.split("/").filter((p) => p);
    let path = "";
    parts.forEach((part, index) => {
      path = path ? `${path}/${part}` : part;
      segments.push({
        text: part,
        path: path,
        clickable: index < parts.length - 1,
      });
    });
  }

  return segments;
});

// Methods
const loadItems = async () => {
  loading.value = true;
  try {
    const result = await api.browseMediaFiles("video", currentPath.value);
    // Add ".." item for navigation back if we're in a subfolder
    if (currentPath.value) {
      const parentPath = currentPath.value.includes("/")
        ? currentPath.value.substring(0, currentPath.value.lastIndexOf("/"))
        : "";
      items.value = [
        {
          id: "..",
          name: "..",
          path: parentPath,
          is_folder: true,
          media_type: "folder",
          size: 0,
          uri: "",
        },
        ...result,
      ];
    } else {
      items.value = result;
    }
  } catch (error) {
    console.error("Failed to load video files:", error);
    items.value = [];
  }
  loading.value = false;
};

const navigateTo = (path: string) => {
  currentPath.value = path;
  router.push({ path: "/video", query: path ? { path } : undefined });
};

const navigateToSegment = (path: string | null) => {
  if (path === "__browse__") {
    router.push({ path: "/browse" });
  } else if (path === null) {
    router.push({ path: "/video" });
  } else {
    router.push({ path: "/video", query: { path } });
  }
};

const handleItemClick = (item: MediaFileItem) => {
  if (item.is_folder) {
    navigateTo(item.path);
  } else {
    playVideo(item);
  }
};

const playVideo = (item: MediaFileItem) => {
  currentVideo.value = item;
  showPlayerDialog.value = true;
};

const onPlayerClose = () => {
  if (videoPlayer.value) {
    videoPlayer.value.pause();
    videoPlayer.value.src = "";
  }
  currentVideo.value = null;
};

const onVideoError = (event: Event) => {
  console.error("Video playback error:", event);
};

const getSubtitle = (item: MediaFileItem): string => {
  if (item.id === "..") {
    return "folder";
  }
  if (item.is_folder) {
    return t("video_files.items_count", { count: item.children_count || 0 });
  }
  return formatFileSize(item.size);
};

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
};

const triggerFileUpload = () => {
  fileInput.value?.click();
};

const triggerFolderUpload = () => {
  folderInput.value?.click();
};

const handleFileSelect = async (event: Event) => {
  const input = event.target as HTMLInputElement;
  const files = input.files;
  if (!files || files.length === 0) return;

  // Filter only video files
  const videoExtensions = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv"];
  const videoFiles = Array.from(files).filter((f) => {
    const ext = f.name.toLowerCase().substring(f.name.lastIndexOf("."));
    return videoExtensions.includes(ext) || f.type.startsWith("video/");
  });

  if (videoFiles.length === 0) {
    alert(t("video_files.no_video_files"));
    input.value = "";
    return;
  }

  totalFilesToUpload.value = videoFiles.length;
  uploadedCount.value = 0;
  showUploadDialog.value = true;

  for (let i = 0; i < videoFiles.length; i++) {
    const file = videoFiles[i];
    // For folder uploads, preserve relative path
    const relativePath = (file as any).webkitRelativePath || "";
    const folderPart = relativePath ? relativePath.substring(0, relativePath.lastIndexOf("/")) : "";
    const targetFolder = currentPath.value
      ? folderPart
        ? `${currentPath.value}/${folderPart}`
        : currentPath.value
      : folderPart;

    uploadingFileName.value = file.name;
    uploadProgress.value = 0;

    try {
      // Use HTTP multipart upload for large files
      const formData = new FormData();
      formData.append("file", file);

      // Get base URL from API
      const baseUrl = api.baseUrl || window.location.origin;
      const uploadUrl = `${baseUrl}/upload?media_type=video&folder_path=${encodeURIComponent(targetFolder)}`;

      const xhr = new XMLHttpRequest();

      await new Promise<void>((resolve, reject) => {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            uploadProgress.value = Math.round((e.loaded / e.total) * 100);
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve();
          } else {
            reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
          }
        };

        xhr.onerror = () => reject(new Error("Network error"));
        xhr.open("POST", uploadUrl);
        xhr.send(formData);
      });

      uploadedCount.value++;
    } catch (error: any) {
      console.error("Failed to upload file:", file.name, error);
      alert(`${t("video_files.upload_failed")}: ${file.name}\n${error?.message || error}`);
    }
  }

  showUploadDialog.value = false;
  input.value = ""; // Reset input
  loadItems(); // Refresh list
};

const createFolder = async () => {
  if (!newFolderName.value.trim()) return;

  creating.value = true;
  try {
    await api.createMediaFolder(newFolderName.value.trim(), "video", currentPath.value);
    showCreateFolderDialog.value = false;
    newFolderName.value = "";
    loadItems();
  } catch (error) {
    console.error("Failed to create folder:", error);
  }
  creating.value = false;
};

const confirmDelete = (item: MediaFileItem) => {
  itemToDelete.value = item;
  showDeleteDialog.value = true;
};

const deleteItem = async () => {
  if (!itemToDelete.value) return;

  deleting.value = true;
  try {
    await api.deleteMediaItem(itemToDelete.value.path, "video");
    showDeleteDialog.value = false;
    itemToDelete.value = null;
    loadItems();
  } catch (error) {
    console.error("Failed to delete item:", error);
  }
  deleting.value = false;
};

const openMoveDialog = async (item: MediaFileItem) => {
  itemToMove.value = item;
  selectedDestFolder.value = "";

  try {
    const folders = await api.listMediaFolders("video");
    // Filter out the current item's folder (can't move to itself)
    availableFolders.value = folders.filter((f) => {
      // Don't show the item's current parent folder
      const itemParent = item.path.includes("/")
        ? item.path.substring(0, item.path.lastIndexOf("/"))
        : "";
      // Don't show the item itself if it's a folder
      if (item.is_folder && f.path === item.path) return false;
      // Don't show subfolders of the item if it's a folder
      if (item.is_folder && f.path.startsWith(item.path + "/")) return false;
      return f.path !== itemParent;
    });
  } catch (error) {
    console.error("Failed to load folders:", error);
    availableFolders.value = [{ name: "/", path: "" }];
  }

  showMoveDialog.value = true;
};

const moveItem = async () => {
  if (!itemToMove.value) return;

  moving.value = true;
  try {
    await api.moveMediaItem(itemToMove.value.path, selectedDestFolder.value, "video");
    showMoveDialog.value = false;
    itemToMove.value = null;
    loadItems();
  } catch (error: any) {
    console.error("Failed to move item:", error);
    alert(`${t("video_files.move_failed")}: ${error?.message || error}`);
  }
  moving.value = false;
};

// Watch for route query changes
watch(
  () => route.query.path,
  (newPath) => {
    currentPath.value = (newPath as string) || "";
    loadItems();
  },
  { immediate: true }
);

onMounted(() => {
  currentPath.value = (route.query.path as string) || "";
  loadItems();
});
</script>

<style scoped>
.v-list-item {
  cursor: pointer;
}
.v-list-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.08);
}

/* Grid view styles */
.video-card {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}
.video-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
.card-thumbnail {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  position: relative;
}
.folder-card .card-thumbnail {
  background: linear-gradient(135deg, #2d2d2d 0%, #1a1a1a 100%);
}
.video-icon {
  opacity: 0.7;
}
.thumbnail-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.play-overlay {
  position: absolute;
  opacity: 0;
  transition: opacity 0.2s;
}
.video-card:hover .play-overlay {
  opacity: 1;
}

/* Video player styles */
.video-player-card {
  background: #000;
}
.video-player-card .v-card-title {
  background: rgba(0, 0, 0, 0.8);
  color: white;
}
.video-element {
  width: 100%;
  max-height: 70vh;
  display: block;
}

/* Breadcrumbs styles (same as BrowseView) */
.breadcrumb-container {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
  max-width: 100%;
}

.breadcrumb-segment {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.breadcrumb-link {
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  text-decoration: underline;
  font-family: inherit;
  font-size: inherit;
  padding: 0;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.breadcrumb-link:hover {
  opacity: 0.7;
}

.breadcrumb-text {
  color: inherit;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.breadcrumb-separator {
  opacity: 0.5;
  margin: 0 2px;
  flex-shrink: 0;
}
</style>
