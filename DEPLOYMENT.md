# Free deployment

## 1. Persistent database: Neon

Create a free Neon PostgreSQL project and copy its pooled connection string.
Keep it private; it will be used as Render's `DATABASE_URL`.

## 2. Django dashboard/API: Render

1. Commit and push this repository to GitHub.
2. In Render, create a **Blueprint** from the repository. Render reads
   `render.yaml`.
3. When prompted, set `DATABASE_URL` to the Neon connection string.
4. After deployment, copy the generated `IOT_API_KEY` from the Render
   environment into the ESP32's local `secrets.h`.
5. Create the first administrator from Render Shell:

   `python manage.py createsuperuser`

The expected URL is:

`https://aquapulse-water-regulator.onrender.com`

If Render assigns a different service name, update `ALLOWED_HOSTS`,
`QR_BASE_URL`, and `CSRF_TRUSTED_ORIGINS`.

## 3. Flutter web/PWA: GitHub Pages

In the `aquapulse-mobile-app` GitHub repository:

1. Open **Settings → Pages** and select **GitHub Actions** as the source.
2. Add an Actions repository variable named `API_BASE_URL` with:

   `https://aquapulse-water-regulator.onrender.com/api`

3. Push the workflow added under `.github/workflows/deploy-pages.yml`.

The expected PWA URL is:

`https://mohali-jr2.github.io/aquapulse-mobile-app/`

## 4. ESP32

Set the public server URL and the same Render `IOT_API_KEY` in `secrets.h`,
then flash the ESP32 again. The device must use the HTTPS Render URL, not a
private `192.168.x.x` address.

## Free-tier limitations

Render's free service sleeps after inactivity, so the first request can take
about a minute. Local uploaded media is not persistent on Render; use an
object-storage service before relying on profile-photo uploads in production.
