# My DashboardKDV 1.0.0

Персональный веб-дашборд для быстрых ссылок на приложения.

## Возможности

- приложения и категории;
- избранное и поиск;
- светлая и тёмная тема;
- emoji, локальные иконки, иконки по URL и favicon;
- фоновое изображение с настройкой затемнения;
- интеграция статуса Emby;
- экспорт и импорт настроек в JSON;
- SQLite в `./data`.

Docker используется только для запуска Dashboard.

## Установка из готового Docker-образа

Требуется установленный Docker Desktop.

```powershell
docker compose pull
docker compose up -d
```

Открой:

```text
http://localhost:8080
```

Остановка:

```powershell
docker compose down
```

Обновление до последнего образа:

```powershell
docker compose pull
docker compose up -d
```

Данные Dashboard хранятся в `./data` и не входят в Docker-образ.

## Локальная разработка

Для сборки из исходников:

```powershell
docker compose -f docker-compose.build.yml build --no-cache
docker compose -f docker-compose.build.yml up -d
```

Остановка:

```powershell
docker compose -f docker-compose.build.yml down
```

## Docker image

```text
ghcr.io/podpeedami/my-dashboardkdv:latest
ghcr.io/podpeedami/my-dashboardkdv:1.0.0
```

GitHub Actions автоматически собирает и публикует образ в GitHub Container Registry при push в `main` и при создании тега `v*.*.*`.

## Хранение данных

Локальная папка:

```text
data/
├── dashboard.db
├── icons/
└── backgrounds/
```

Эта папка специально исключена из Git и Docker build context.
