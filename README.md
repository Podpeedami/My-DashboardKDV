# My DashboardKDV

**My DashboardKDV** — персональная веб-панель для удобного запуска и организации приложений и сервисов в одном месте.

## Возможности

- 📱 Добавление, редактирование и удаление приложений.
- 🗂️ Создание и управление категориями.
- ⭐ Избранные приложения.
- 🔎 Поиск по панели.
- 😀 Emoji для приложений и категорий.
- 🖼️ Иконки из локального файла.
- 🌐 Иконки по URL.
- 🔎 Автоматическое получение favicon приложения.
- ☀️ Светлая и 🌙 тёмная тема.
- 🖼️ Пользовательский фон: файл или URL, затемнение и удаление.
- ⚙️ Экспорт и импорт настроек.
- 📺 Интеграция с Emby для отображения состояния и активных сессий.
- 💾 SQLite для хранения данных.
- 🐳 Docker / Docker Compose для установки и запуска.

## docker-compose.yml

Для стандартной установки используется готовый Docker-образ из GitHub Container Registry.

Файл `docker-compose.yml`:

```yaml
services:
  dashboard:
    image: ghcr.io/podpeedami/my-dashboardkdv:latest
    container_name: my-dashboardkdv
    ports:
      - "8080:8000"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

Запуск:

```bash
docker compose pull
docker compose up -d
```

Проверка:

```bash
docker ps
```

Открыть Dashboard:

```text
http://localhost:8080
```

## Быстрая установка

Требования:

- Docker
- Docker Compose

Проверка:

```bash
docker --version
docker compose version
```

Клонирование проекта:

```bash
git clone https://github.com/Podpeedami/My-DashboardKDV.git
cd My-DashboardKDV
```

Запуск готового Docker-образа:

```bash
docker compose pull
docker compose up -d
```

Открыть:

```text
http://localhost:8080
```

Проверить контейнер:

```bash
docker ps
```

## Docker-образ

Используется GitHub Container Registry:

```text
ghcr.io/podpeedami/my-dashboardkdv:latest
```

Обычная установка использует готовый образ и не требует локальной сборки.

## Данные

Пользовательские данные находятся в:

```text
data/
├── dashboard.db
├── icons/
└── backgrounds/
```

Docker подключает каталог:

```yaml
volumes:
  - ./data:/app/data
```

Не удаляйте `data/`, если хотите сохранить приложения, категории, иконки, фон и данные базы.

## Резервная копия

В настройках панели доступны:

- 💾 экспорт настроек;
- 📥 импорт настроек.

Файл экспорта:

```text
My-DashboardKDV-settings.json
```

Перед крупными обновлениями рекомендуется дополнительно сделать копию каталога `data/`.

## Иконки

Для приложения или категории можно использовать:

```text
😀 Emoji
🖼️ Локальный файл
🌐 URL изображения
🔎 Favicon сайта
```

Пользовательские иконки хранятся в:

```text
data/icons/
```

## Фон

В настройках можно:

- загрузить изображение с компьютера;
- указать URL;
- настроить затемнение;
- удалить фон.

Пользовательские фоны хранятся в:

```text
data/backgrounds/
```

## Темы

Доступны:

```text
☀️ Светлая
🌙 Тёмная
```

Выбранная тема сохраняется в браузере.

## Emby

Для подключения Emby откройте настройки My DashboardKDV и укажите адрес сервера и API-ключ.

Пример:

```text
http://192.168.1.100:8096
```

API-ключ Emby не следует публиковать в GitHub или помещать в публичные конфигурационные файлы.

## Обновление

```bash
docker compose pull
docker compose down
docker compose up -d
```

Проверка:

```bash
docker ps
```

Если браузер показывает старый интерфейс:

```text
Ctrl + F5
```

## Остановка

```bash
docker compose down
```

Повторный запуск:

```bash
docker compose up -d
```

## Логи

```bash
docker compose logs -f
```

Последние строки:

```bash
docker compose logs --tail=200
```

## GitHub

Репозиторий:

https://github.com/Podpeedami/My-DashboardKDV

Основные команды:

```bash
git status
git add .
git commit -m "Update My DashboardKDV"
git push origin main
```

## Структура проекта

```text
My-DashboardKDV/
├── app/
│   ├── main.py
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── style.css
├── data/
│   ├── dashboard.db
│   ├── icons/
│   └── backgrounds/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .gitignore
└── README.md
```

## Безопасность

Не публикуйте:

- `data/dashboard.db`;
- API-ключ Emby;
- пароли;
- секретные токены;
- приватные резервные копии.

Каталог `data/` должен быть исключён из Git через `.gitignore`.

## Диагностика

Если контейнер не запускается:

```bash
docker ps -a
docker compose logs --tail=200
```

Если образ не скачивается:

```bash
docker pull ghcr.io/podpeedami/my-dashboardkdv:latest
```

Если порт `8080` занят, измените внешний порт в `docker-compose.yml`, например:

```yaml
ports:
  - "8081:8000"
```

Тогда приложение будет доступно по адресу:

```text
http://localhost:8081
```

## Версия

**My DashboardKDV 1.0.0**

---

**GitHub:** https://github.com/Podpeedami/My-DashboardKDV  
**Docker:** `ghcr.io/podpeedami/my-dashboardkdv:latest`
