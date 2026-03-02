import sys
import pandas as pd
from pathlib import Path

GIST_RAW_URL = (
    "https://gist.githubusercontent.com/lapanquecita/1b819ec5373f9304efc52149e96a91b7/raw/"
    "poblacion.csv"
)

HELP = f"""
Genera un archivo CSV de centroides municipales (cvegeo, lat, lon, entidad, municipio)
utilizando el dataset público (INEGI 2020) publicado en GitHub Gist:
{GIST_RAW_URL}

Uso 1 (rápido, todo el país):
    python make_centroides_from_gist.py
    -> crea 'centroides_municipios_full.csv'

Uso 2 (filtrado por tu CSV con cvegeo):
    python make_centroides_from_gist.py ruta/a/tu_datos.csv salida.csv
    -> detecta cvegeo únicos en tu CSV y crea 'salida.csv' con solo esos centroides
       (si tu CSV no tiene cvegeo, intenta construirlo desde ID_ENTIDAD + ID_MUNICIPIO)
"""

def load_centroids_from_gist() -> pd.DataFrame:
    df = pd.read_csv(GIST_RAW_URL)
    # normaliza encabezados esperados en el gist
    df.columns = [str(c).strip().lower() for c in df.columns]
    # construye cvegeo = EE(2) + MMM(3)
    df["cvegeo"] = (
        df["clave_entidad"].astype(str).str.zfill(2)
        + df["clave_municipio"].astype(str).str.zfill(3)
    )
    # renombra a lat/lon
    out = df.rename(columns={"latitud": "lat", "longitud": "lon"})[
        ["cvegeo", "lat", "lon", "entidad", "municipio"]
    ].copy()
    # asegura numéricos
    out["lat"] = pd.to_numeric(out["lat"], errors="coerce")
    out["lon"] = pd.to_numeric(out["lon"], errors="coerce")
    # descarta NaN
    out = out.dropna(subset=["lat", "lon"])
    return out

def ensure_cvegeo(df: pd.DataFrame) -> pd.Series:
    cols = [c.lower() for c in df.columns]
    df.columns = cols
    if "cvegeo" in df.columns:
        return df["cvegeo"].astype(str).str.zfill(5)
    # intenta con id_entidad + id_municipio
    if "id_entidad" in df.columns and "id_municipio" in df.columns:
        return df["id_entidad"].astype(str).str.zfill(2) + df["id_municipio"].astype(str).str.zfill(3)
    raise ValueError("No se encontró 'cvegeo' ni ('id_entidad' + 'id_municipio') en el CSV de entrada")

def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        # modo rápido: todo el país
        cent = load_centroids_from_gist()
        out_path = Path("centroides_municipios_full.csv")
        cent.to_csv(out_path, index=False)
        print(f"OK: creado {out_path.resolve()} con {len(cent):,} filas")
        print(HELP)
        return 0

    in_csv = Path(argv[0])
    out_csv = Path(argv[1]) if len(argv) > 1 else Path("centroides_municipios.csv")

    # carga claves del CSV del usuario
    df_user = pd.read_csv(in_csv)
    cves = ensure_cvegeo(df_user).dropna().astype(str).str.zfill(5).unique().tolist()

    cent = load_centroids_from_gist()
    cent_sel = cent[cent["cvegeo"].isin(cves)].copy()
    cent_sel.to_csv(out_csv, index=False)
    print(f"OK: creado {out_csv.resolve()} con {len(cent_sel):,} filas (de {len(cent):,} total)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())