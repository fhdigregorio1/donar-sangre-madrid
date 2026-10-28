# Donar Sangre Madrid

Mapa de los puntos de donación de sangre de la Comunidad de Madrid: unidades móviles por día y centros fijos.
Iniciativa independiente de Felipe Di Gregorio, sin vinculación con la Comunidad de Madrid ni el SERMAS.
Los datos salen de <https://donarsangre.sanidadmadrid.org/moviles.aspx>.

- `index.html`: la página (Leaflet + OpenStreetMap). Lee `data/puntos.json`.
- `scripts/update.py`: lee la web, asigna coordenadas y escribe `data/puntos.json`.
- `data/seeds.json`: posiciones ya verificadas. Las direcciones nuevas se buscan en Nominatim (OpenStreetMap) y se guardan en `data/coords_cache.json`.
- `data/fijos.json`: centros fijos (de `fijos.aspx` y fichas de detalle, más `data/fijos_extra.json`).
- `data/aviso.json`: banda de aviso superior (`activo`, `hasta`, texto y enlace).
- `.github/workflows/actualizar.yml`: ejecuta el script dos veces al día y sube los cambios.

## Publicar
1. En el repositorio: Settings → Pages → *Deploy from a branch* → rama `main`, carpeta `/ (root)`.
2. La página queda en `https://<usuario>.github.io/<repositorio>/`.
3. Para forzar una actualización: pestaña Actions → *Actualizar puntos de donación* → Run workflow.

## Probar sin red
    python scripts/update.py --offline tests/sample_rows.json --hoy 2026-10-28
