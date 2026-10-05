# Быстрая установка My DashboardKDV

## Требования

Установите Docker Desktop.

## Установка

Скачайте `docker-compose.yml` из этого репозитория в отдельную папку, например:

```powershell
mkdir C:\My-DashboardKDV
cd C:\My-DashboardKDV
```

Поместите туда `docker-compose.yml` и выполните:

```powershell
docker compose pull
docker compose up -d
```

Откройте:

```text
http://localhost:8080
```

## Обновление

```powershell
docker compose pull
docker compose up -d
```

## Остановка

```powershell
docker compose down
```

## Локальная сборка для разработки

В полном клоне репозитория:

```powershell
docker compose -f docker-compose.build.yml build --no-cache
docker compose -f docker-compose.build.yml up -d
```
