# План реалізації: Функція "Розклад" для Music Assistant

## Огляд

Створення функції планування музичного відтворення з підтримкою:
- Вибір часового інтервалу (початок/кінець)
- Вибір плеєрів та налаштування гучності для кожного
- Вибір плейлистів або окремих треків
- Групування плеєрів для синхронного відтворення
- Зациклення контенту в заданому інтервалі
- Рекламні оголошення (завантаження файлів + розклад)

## Технічні рішення

- **UI**: Повна реалізація (Backend + Frontend)
- **Сховище**: SQLite база даних
- **Оголошення**: Завантаження файлів на сервер через форму розкладу

---

## Фаза 1: Моделі даних та база даних

### 1.1 Файл моделей
**Створити**: `/music_assistant/models/schedule.py`

```python
@dataclass
class PlayerVolumeSetting:
    player_id: str
    volume: int  # 0-100

@dataclass
class ScheduledAnnouncement:
    announcement_id: str
    name: str
    file_path: str
    time: str  # HH:MM
    repeat_interval: int | None = None  # хвилини, None = одноразово

@dataclass
class Schedule:
    schedule_id: str
    name: str
    enabled: bool
    start_time: str  # HH:MM
    end_time: str    # HH:MM
    days_of_week: list[int]  # 0=Пн, 6=Нд
    media_items: list[str]   # URI плейлистів/треків
    players: list[PlayerVolumeSetting]
    group_players: bool = False
    loop_content: bool = True
    shuffle: bool = False
    announcements: list[ScheduledAnnouncement] = field(default_factory=list)
```

### 1.2 SQLite схема

```sql
CREATE TABLE IF NOT EXISTS schedules (
    schedule_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    days_of_week JSON NOT NULL,
    media_items JSON NOT NULL,
    players JSON NOT NULL,
    group_players BOOLEAN DEFAULT 0,
    loop_content BOOLEAN DEFAULT 1,
    shuffle BOOLEAN DEFAULT 0,
    announcements JSON,
    created_at INTEGER,
    updated_at INTEGER
);
```

---

## Фаза 2: Backend контролер

### 2.1 Основний контролер
**Створити**: `/music_assistant/controllers/schedule.py`

```python
class ScheduleController(CoreController):
    domain: str = "schedule"

    async def setup(self, config: CoreConfig) -> None:
        # Ініціалізація БД
        # Створення папки для оголошень
        # Запуск планувальника

    async def close(self) -> None:
        # Зупинка планувальника
```

### 2.2 API команди

| Команда | Опис |
|---------|------|
| `schedule/all` | Отримати всі розклади |
| `schedule/get` | Отримати розклад за ID |
| `schedule/create` | Створити розклад |
| `schedule/update` | Оновити розклад |
| `schedule/delete` | Видалити розклад |
| `schedule/enable` | Увімкнути/вимкнути |
| `schedule/trigger` | Запустити вручну |
| `schedule/stop` | Зупинити активний |
| `schedule/upload_announcement` | Завантажити аудіофайл оголошення |
| `schedule/delete_announcement` | Видалити файл оголошення |

### 2.3 Логіка планувальника

```python
async def _scheduler_loop(self) -> None:
    """Головний цикл - перевірка кожні 30 секунд."""
    while not self.mass.closing:
        await self._check_schedules()
        await asyncio.sleep(30)

async def _check_schedules(self) -> None:
    current = datetime.now()
    for schedule in await self._get_enabled_schedules():
        if self._should_start(schedule, current):
            await self._start_schedule(schedule)
        elif self._should_stop(schedule, current):
            await self._stop_schedule(schedule)

        if self._is_active(schedule):
            await self._check_announcements(schedule, current)
```

### 2.4 Запуск розкладу

```python
async def _start_schedule(self, schedule: Schedule) -> None:
    # 1. Групувати плеєри (якщо потрібно)
    if schedule.group_players:
        await self.mass.players.cmd_set_members(...)

    # 2. Встановити гучність для кожного плеєра
    for p in schedule.players:
        await self.mass.players.cmd_volume_set(p.player_id, p.volume)

    # 3. Налаштувати повтор
    if schedule.loop_content:
        self.mass.player_queues.set_repeat(queue_id, RepeatMode.ALL)

    # 4. Запустити відтворення
    await self.mass.player_queues.play_media(
        queue_id=schedule.players[0].player_id,
        media=schedule.media_items,
        option=QueueOption.REPLACE
    )
```

### 2.5 Оголошення

```python
async def _play_scheduled_announcement(self, schedule, announcement) -> None:
    """Відтворити оголошення на всіх плеєрах розкладу."""
    # Існуючий API автоматично паузить музику та відновлює
    for player in schedule.players:
        await self.mass.players.play_announcement(
            player_id=player.player_id,
            url=f"http://{self.mass.streams.publish_ip}:{self.mass.streams.publish_port}/announcement/{announcement.announcement_id}.mp3"
        )
```

### 2.6 Завантаження файлів оголошень

```python
@api_command("schedule/upload_announcement")
async def upload_announcement(
    self,
    name: str,
    file_data: str,  # Base64 encoded
    file_name: str
) -> ScheduledAnnouncement:
    """Завантажити аудіофайл оголошення."""
    announcement_id = shortuuid.random(8)
    file_path = self._announcements_path / f"{announcement_id}_{file_name}"

    # Декодувати та зберегти файл
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(base64.b64decode(file_data))

    return ScheduledAnnouncement(
        announcement_id=announcement_id,
        name=name,
        file_path=str(file_path),
        time="",
        repeat_interval=None
    )
```

---

## Фаза 3: Інтеграція з ядром

### 3.1 Реєстрація контролера
**Модифікувати**: `/music_assistant/mass.py`

```python
from music_assistant.controllers.schedule import ScheduleController

class MusicAssistant:
    schedule: ScheduleController

    async def _setup_core(self) -> None:
        # ... існуючий код ...
        self.schedule = ScheduleController(self)
        await self.schedule.setup(await self.config.get_core_config("schedule"))
```

### 3.2 Константи
**Модифікувати**: `/music_assistant/constants.py`

```python
DB_TABLE_SCHEDULES: Final[str] = "schedules"
ANNOUNCEMENTS_DIR: Final[str] = "announcements"
```

---

## Фаза 4: Frontend (окремий репозиторій)

### 4.1 Клонувати frontend репозиторій
```bash
git clone https://github.com/music-assistant/frontend
```

### 4.2 Структура компонентів

```
src/
  views/
    ScheduleView.vue           # Список розкладів
    ScheduleEditView.vue       # Форма створення/редагування
  components/
    schedule/
      ScheduleCard.vue         # Картка розкладу
      ScheduleForm.vue         # Основна форма
      PlayerVolumeSelector.vue # Вибір плеєрів + гучність
      TimeRangePicker.vue      # Вибір часу
      DaysOfWeekPicker.vue     # Вибір днів
      MediaPicker.vue          # Вибір плейлистів/треків
      AnnouncementManager.vue  # Завантаження та розклад оголошень
```

### 4.3 Маршрутизація

```javascript
{
  path: '/schedule',
  name: 'schedule',
  component: ScheduleView,
  meta: { title: 'Розклад', icon: 'mdi-calendar-clock' }
},
{
  path: '/schedule/new',
  name: 'schedule-new',
  component: ScheduleEditView
},
{
  path: '/schedule/:id/edit',
  name: 'schedule-edit',
  component: ScheduleEditView
}
```

### 4.4 Навігаційне меню

Додати пункт "Розклад" в ліве меню з іконкою `mdi-calendar-clock`

### 4.5 Локалізація (uk_UA)

```json
{
  "schedule": {
    "title": "Розклад",
    "new": "Новий розклад",
    "edit": "Редагувати розклад",
    "name": "Назва",
    "start_time": "Час початку",
    "end_time": "Час завершення",
    "days": "Дні тижня",
    "players": "Плеєри",
    "volume": "Гучність",
    "media": "Музика",
    "group_players": "Групувати плеєри",
    "loop": "Повторювати",
    "shuffle": "Перемішати",
    "announcements": "Оголошення",
    "add_announcement": "Додати оголошення",
    "upload_file": "Завантажити файл",
    "announcement_time": "Час оголошення",
    "repeat_every": "Повторювати кожні",
    "minutes": "хвилин",
    "enabled": "Увімкнено",
    "disabled": "Вимкнено",
    "save": "Зберегти",
    "delete": "Видалити",
    "confirm_delete": "Видалити цей розклад?"
  },
  "days": {
    "mon": "Пн",
    "tue": "Вт",
    "wed": "Ср",
    "thu": "Чт",
    "fri": "Пт",
    "sat": "Сб",
    "sun": "Нд"
  }
}
```

---

## Порядок реалізації

### Етап 0: Підготовка
0. [x] Клонувати frontend репозиторій ✅ (вже є в /root/music-assistant-frontend)

### Етап 1: Backend основа ✅ ЗАВЕРШЕНО
1. [x] Створити `/music_assistant/models/schedule.py` ✅
   - Schedule, PlayerVolumeSetting, ScheduledAnnouncement, ScheduleState
   - Серіалізація через DataClassDictMixin
2. [x] Додати константи в `constants.py` ✅
   - DB_TABLE_SCHEDULES, ANNOUNCEMENTS_DIR, SCHEDULE_CHECK_INTERVAL
3. [x] Створити `/music_assistant/controllers/schedule.py` (CRUD) ✅
4. [x] Реалізувати SQLite схему та операції ✅

### Етап 2: Логіка планувальника ✅ ЗАВЕРШЕНО
5. [x] Реалізувати `_scheduler_loop()` ✅ - перевірка кожні 30 сек
6. [x] Реалізувати `_start_schedule()` / `_stop_schedule()` ✅
7. [x] Інтеграція з player_queues (play_media, repeat) ✅
8. [x] Інтеграція з players (volume, grouping) ✅

### Етап 3: Оголошення ✅ ЗАВЕРШЕНО
9. [x] Реалізувати завантаження файлів ✅ - upload_announcement API
10. [x] Реалізувати роздачу файлів через file:// ✅
11. [x] Реалізувати розклад оголошень ✅ - _check_announcements, _play_announcement

### Етап 4: Інтеграція ✅ ЗАВЕРШЕНО
12. [x] Зареєструвати контролер в `mass.py` ✅
13. [x] Тестування API через WebSocket ✅ - базове тестування пройдено

### Етап 5: Frontend ✅ ЗАВЕРШЕНО
14. [x] Клонувати frontend репозиторій ✅
15. [x] Створити компоненти ✅
    - ScheduleView.vue - список розкладів
    - ScheduleEditView.vue - форма створення/редагування
16. [x] Додати маршрути та навігацію ✅
    - /schedule - список
    - /schedule/new - створення
    - /schedule/:id/edit - редагування
    - Пункт меню "Розклад" з іконкою CalendarClock
17. [x] Додати локалізацію ✅
    - en.json - англійська
    - uk_UA.json - українська
18. [ ] Тестування UI (потребує запуску frontend)

---

## Ключові файли

### Backend (створити/модифікувати):
- `/music_assistant/models/schedule.py` - ✅ СТВОРЕНО
- `/music_assistant/controllers/schedule.py` - ✅ СТВОРЕНО
- `/music_assistant/mass.py` - ✅ модифіковано (реєстрація)
- `/music_assistant/constants.py` - ✅ модифіковано (константи)

### Реалізовані API команди:
| Команда | Статус |
|---------|--------|
| `schedule/all` | ✅ |
| `schedule/get` | ✅ |
| `schedule/create` | ✅ |
| `schedule/update` | ✅ |
| `schedule/delete` | ✅ |
| `schedule/enable` | ✅ |
| `schedule/trigger` | ✅ |
| `schedule/stop` | ✅ |
| `schedule/upload_announcement` | ✅ |
| `schedule/delete_announcement` | ✅ |
| `schedule/list_announcements` | ✅ |

### Референси (читати для патернів):
- `/music_assistant/controllers/player_queues.py` - play_media, repeat
- `/music_assistant/controllers/players/player_controller.py` - volume, announcements, grouping
- `/music_assistant/controllers/config.py` - збереження налаштувань
- `/music_assistant/helpers/database.py` - робота з SQLite

### Frontend (окремий репозиторій):
- Локація: `/root/music-assistant-frontend`
- Оригінал: `github.com/music-assistant/frontend`

#### Створені/модифіковані файли:
- `/src/views/ScheduleView.vue` - ✅ СТВОРЕНО (список розкладів)
- `/src/views/ScheduleEditView.vue` - ✅ СТВОРЕНО (форма редагування)
- `/src/plugins/router.ts` - ✅ модифіковано (маршрути /schedule)
- `/src/constants.ts` - ✅ модифіковано (DEFAULT_MENU_ITEMS)
- `/src/components/navigation/utils/getMenuItems.ts` - ✅ модифіковано (пункт меню)
- `/src/translations/en.json` - ✅ модифіковано (англійська локалізація)
- `/src/translations/uk_UA.json` - ✅ модифіковано (українська локалізація)
