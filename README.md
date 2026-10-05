# My DashboardKDV 4.4

Dashboard-only web application with application/category management, light/dark themes, custom icons, Emby status integration, and a customizable background image.

## Background

In **Settings → Background image** you can upload an image from the computer or download it from a public URL. The image is stored under `data/backgrounds`, so it survives Docker rebuilds. You can adjust background opacity and remove the image. The background image is embedded into the JSON export so it can be restored on another installation.

## Run

```powershell
docker compose build --no-cache
docker compose up -d
```

Open `http://localhost:8080`.
