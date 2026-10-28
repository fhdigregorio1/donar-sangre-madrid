# Donar Sangre Madrid

Mapa de los puntos móviles de donación de sangre de la Comunidad de Madrid, por día y municipio.
Los datos salen de <https://donarsangre.sanidadmadrid.org/moviles.aspx>.

- `index.html`: la página (Leaflet + OpenStreetMap). Lee `data/puntos.json`.
- `scripts/update.py`: lee la web, asigna coordenadas y escribe `data/puntos.json`.
- `data/seeds.json`: posiciones ya verificadas. Las direcciones nuevas se buscan en Nominatim (OpenStreetMap) y se guardan en `data/coords_cache.json`.
- `.github/workflows/actualizar.yml`: ejecuta el script cada día y sube los cambios.

## Publicar
1. En el repositorio: Settings → Pages → *Deploy from a branch* → rama `main`, carpeta `/ (root)`.
2. La página queda en `https://<usuario>.github.io/<repositorio>/`.
3. Para forzar una actualización: pestaña Actions → *Actualizar puntos de donación* → Run workflow.

## Probar sin red
    python scripts/update.py --offline tests/sample_rows.json --hoy 2026-10-28
