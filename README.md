# Legis 2025

Proyecto base en Django que replica el portal de resultados para las Elecciones Legislativas 2025 en Argentina. Utiliza AdminLTE 3 (sobre Bootstrap 4) para ofrecer un panel público con métricas de participación, cobertura de mesas escrutadas y síntesis por distrito electoral.

## Requisitos

- Python 3.13
- Entorno virtual (se crea automáticamente con la configuración de Copilot)

## Puesta en marcha

1. Instalar dependencias:

   ```powershell
   D:/python/projects/legis2025/.venv/Scripts/python.exe -m pip install -r requirements.txt
   ```

2. Aplicar migraciones iniciales:

   ```powershell
   D:/python/projects/legis2025/.venv/Scripts/python.exe manage.py migrate
   ```

3. Ejecutar el servidor de desarrollo:

   ```powershell
   D:/python/projects/legis2025/.venv/Scripts/python.exe manage.py runserver
   ```

4. Visitar `http://localhost:8000/` para abrir el panel principal con los resultados preliminares.

### Cargar datos de ejemplo

```powershell
D:/python/projects/legis2025/.venv/Scripts/python.exe manage.py loaddata ^
   elections/fixtures/sample_districts.json ^
   elections/fixtures/sample_lists.json ^
   elections/fixtures/sample_scrutinies.json
```

Para utilizar el padrón completo de distritos, se incluye `elections/fixtures/districts_2025.json` generado a partir de los archivos oficiales en la carpeta `docs/`.

### Carga manual de porcentajes

El portal incorpora una herramienta de carga en `http://localhost:8000/ingest/`:

1. Elegir el distrito y la cámara (Diputados o Senadores).
2. Completar los porcentajes para cada lista, ordenadas según el campo `order`.
3. Guardar los cambios para sobrescribir el escrutinio existente. Los campos en blanco eliminan el registro previo.

El tablero aplica automáticamente:

- Método D'Hondt con umbral del 3 % para Diputados.
- Reparto 2+1 (mayoría y primera minoría) para Senadores.
- Filtro superior para alternar la visualización entre Diputados, Senadores o ambas cámaras.

Los datos de ejemplo para Buenos Aires, Ciudad Autónoma de Buenos Aires y Córdoba utilizan los resultados definitivos de las elecciones legislativas 2023 publicados por la Cámara Nacional Electoral y recopilados por Wikipedia.[^fuente-elecciones-2023]

## Ejecutar pruebas

```powershell
D:/python/projects/legis2025/.venv/Scripts/python.exe manage.py test
```

## Estructura destacada

- `elections/models.py`: modelo de distritos, listas y resultados de escrutinio.
- `elections/admin.py`: administración de datos electorales.
- `portal/views.py`: vista del tablero principal con filtros por cámara, participación y resultados por provincia.
- `templates/portal/base.html`: plantilla base con AdminLTE 3.
- `portal/templates/portal/dashboard.html`: layout del tablero con métricas, filtro de cámara y tabla de distritos.
- `ingest/views.py`: flujo para cargar porcentajes de escrutinio desde la interfaz protegida.
- `ingest/forms.py`: formularios para selección de distrito/cámara y carga de porcentajes.
- `portal/tests.py`: pruebas automatizadas de asignación de bancas y filtros por cámara.
- `static/portal/css/dashboard.css`: estilos complementarios para listas de resultados y timeline.

[^fuente-elecciones-2023]: «[Elecciones legislativas de Argentina de 2023](https://es.wikipedia.org/wiki/Elecciones_legislativas_de_Argentina_de_2023)», Wikipedia (consulta: 26 de octubre de 2025), con datos de la Cámara Nacional Electoral.
