# Subir ATD_Loreto con GitHub Desktop

Siga estos pasos **una sola vez** para publicar el repositorio.

## 1. Crear el repositorio en GitHub.com

1. Entre a [github.com](https://github.com) con su cuenta institucional.
2. **New repository**
3. Nombre sugerido: `ATD-Loreto-GFP` o `atd-toolbox-loreto`
4. Descripción: *Alertas Tempranas de Deforestación — GFP Subnacional Loreto*
5. **Público** o **Privado** (según política de su institución)
6. **No** marque "Add README" (ya tenemos uno)
7. Crear repositorio y copie la URL, por ejemplo:  
   `https://github.com/SU_USUARIO/ATD-Loreto-GFP.git`

## 2. Abrir el proyecto en GitHub Desktop

1. Abra **GitHub Desktop**
2. **File → Add local repository**
3. Elija esta carpeta:

   ```
   ...\reporte_atd_loreto\output\salidas\ATD_Loreto
   ```

4. Si dice que no es un repositorio git, haga clic en **"create a repository"** o **"initialize git repository"**
   - Name: `ATD-Loreto-GFP`
   - Git ignore: **None** (ya existe `.gitignore` en la carpeta)
   - No inicialice con README

## 3. Primer commit

1. En GitHub Desktop verá todos los archivos listos (toolbox, GDB, logos, guía…)
2. Mensaje del commit (copie y pegue):

   ```
   Publicar paquete ATD Loreto: H1, H2, H3, GDB, logos y demo PDF
   ```

3. Clic en **Commit to main**

## 4. Publicar en GitHub

1. **Publish repository** (botón superior)
2. Nombre: el mismo del paso 1
3. Desmarque "Keep this code private" solo si debe ser público
4. **Publish repository**

Listo. El README con logos se verá en la página principal del repo.

## 5. Actualizaciones futuras

Cada vez que cambie archivos en `ATD_Loreto/`:

1. Abra GitHub Desktop
2. Revise cambios → escriba mensaje → **Commit**
3. **Push origin**

---

## Qué NO se sube (`.gitignore`)

- PDFs que usted genere en `pdfs/` (salvo el ejemplo en `docs/`)
- Imágenes temporales en `imagenes_sentinel/`
- Locks de ArcGIS (`*.lock`)

## Tamaño

El paquete ronda **~35 MB** (GDB incluidas). Cabe en GitHub sin Git LFS.
