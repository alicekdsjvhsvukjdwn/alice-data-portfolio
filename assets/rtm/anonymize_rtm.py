# anonymize_rtm.py
"""
Anonymisation simple pour jeu de données RTM.
- Préserve toutes les colonnes avant (excl.) la colonne 'Revêtement'
- Anonymise toutes les colonnes à partir de 'Revêtement' (incluse)
  * colonnes numériques -> valeurs aléatoires dans [min, max] (type préservé int/float)
  * colonnes catégorielles/textuelles -> mapping vers catégories plausibles
  * option: jitter léger pour colonnes GPS si on choisit de les anonymiser
- Sauvegarde un fichier Excel anonymisé.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import math
import argparse

def find_start_col(columns):
    """Retourne (index, colname) du premier col contenant 'revêtement' ou variantes."""
    targets = ['revêtement', 'revetement', 'revet', 'revêt', 'rev']
    for i, c in enumerate(columns):
        if any(t in str(c).lower() for t in targets):
            return i, c
    return None, None

def anonymize_column(series, col_name, jitter_gps=False):
    """Anonymise une colonne pandas.Series selon son type et son nom."""
    s = series.copy()
    lname = str(col_name).lower()

    # NUMERIC
    if pd.api.types.is_numeric_dtype(s):
        # GPS-like: option to jitter instead of resimuler dans la fourchette
        if any(k in lname for k in ('gps', 'lon', 'lat', 'longitude', 'latitude')) and jitter_gps:
            rng = s.max(skipna=True) - s.min(skipna=True)
            if pd.isna(rng) or rng == 0:
                rng = 0.001
            sd = max(abs(rng) * 0.005, 0.0001)  # 0.5% of range
            noise = np.random.normal(loc=0.0, scale=sd, size=len(s))
            return s + noise

        # otherwise: generate numbers within original range
        non_null = s.dropna()
        if non_null.empty:
            # nothing to base on, return series unchanged
            return s
        orig_min = float(non_null.min())
        orig_max = float(non_null.max())
        if orig_min == orig_max:
            # expand small interval
            orig_min -= 0.5 if orig_min == 0 else abs(orig_min) * 0.1
            orig_max += 0.5 if orig_max == 0 else abs(orig_max) * 0.1

        # Preserve integer-ness if series contains integers
        is_int_like = pd.api.types.is_integer_dtype(s) or all(float(x).is_integer() for x in non_null)
        if is_int_like:
            low = math.floor(orig_min)
            high = math.ceil(orig_max)
            if low == high:
                high = low + 1
            # randint is [low, high), so use high+1 to include high
            return pd.Series(np.random.randint(low, high + 1, size=len(s)), index=s.index)
        else:
            return pd.Series(np.random.uniform(orig_min, orig_max, size=len(s)), index=s.index)

    # TEXT / CATEGORICAL
    else:
        unique_vals = s.dropna().unique()
        n_uniques = len(unique_vals)
        # special cases by column name
        if 'rev' in lname or 'revet' in lname:
            options = ['minéral', 'végétal', 'mixte']
        elif any(k in lname for k in ('surface','sol','pavage','revêtement')):
            options = ['béton', 'goudron', 'terre', 'gravillon']
        elif 'voie' in lname:
            n_opts = min(max(2, n_uniques), 4)
            options = [f'Voie {i+1}' for i in range(n_opts)]
        elif 'ligne' in lname:
            n_opts = min(max(2, n_uniques), 6)
            options = [f'L{i+1}' for i in range(n_opts)]
        elif any(k in lname for k in ('type','categorie','cat','usage','statut')):
            options = [f'Type {i+1}' for i in range(min(6, max(2, n_uniques)))]
        else:
            # generic fallback
            base = ['Option A','Option B','Option C','Option D','Option E','Option F']
            n_opts = min(max(2, n_uniques), len(base))
            options = base[:n_opts]

        # assign random choices (keep NaN as NaN)
        choices = np.random.choice(options, size=len(s))
        res = []
        for i, val in enumerate(s.values):
            if pd.isna(val):
                res.append(np.nan)
            else:
                res.append(choices[i])
        return pd.Series(res, index=s.index)

def anonymize_df(df, start_idx, jitter_gps=False):
    cols = list(df.columns)
    preserve_cols = cols[:start_idx]
    anon_cols = cols[start_idx:]
    df_out = df.copy()

    for col in anon_cols:
        try:
            df_out[col] = anonymize_column(df[col], col, jitter_gps=jitter_gps)
        except Exception as e:
            print(f"⚠️ Erreur sur la colonne {col}: {e}. Conservation des valeurs originales.")
            df_out[col] = df[col]

    return df_out, preserve_cols, anon_cols

def main(input_path, output_path, jitter_gps=False, force_start_idx=None):
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {input_path}")

    # read
    df = pd.read_excel(input_path)
    cols = list(df.columns)
    start_idx, start_col_name = find_start_col(cols)

    if force_start_idx is not None:
        # override start index if user provided
        if 0 <= force_start_idx < len(cols):
            start_idx = force_start_idx
            start_col_name = cols[start_idx]
            print(f"Start index forcé vers {start_idx} ('{start_col_name}')")
        else:
            raise ValueError("force_start_idx hors limites.")

    if start_idx is None:
        # fallback conservative: preserve first 3 columns (ou moins si dataset petit)
        start_idx = min(3, max(0, len(cols)-1))
        start_col_name = cols[start_idx]
        print(f"⚠ 'Revêtement' non trouvé. Anonymisation démarrera à la colonne index {start_idx} ('{start_col_name}').")
    else:
        print(f"Anonymisation à partir de la colonne {start_idx} -> '{start_col_name}'")

    df_anon, preserved, anon_cols = anonymize_df(df, start_idx, jitter_gps=jitter_gps)

    # save
    df_anon.to_excel(output_path, index=False)
    print(f"Fichier anonymisé sauvegardé: {output_path}")
    print(f"Colonnes préservées: {preserved}")
    print(f"Colonnes anonymisées: {anon_cols}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Anonymisation RTM simple")
    parser.add_argument('--input', '-i', default='T1T2T3.xlsx', help='Chemin du fichier Excel d\'entrée')
    parser.add_argument('--output', '-o', default='T1T2T3_anonymized.xlsx', help='Chemin du fichier Excel de sortie')
    parser.add_argument('--jitter-gps', action='store_true', help='Appliquer un petit jitter aux colonnes GPS (si elles sont anonymisées).')
    parser.add_argument('--force-start', type=int, default=None, help='Forcer l index de départ d anonymisation (0-based).')
    args = parser.parse_args()

    main(args.input, args.output, jitter_gps=args.jitter_gps, force_start_idx=args.force_start)

