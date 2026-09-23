#!/usr/bin/env python3
# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later
"""Harmonize ``data/clc_nbs_hazard.csv`` and attach landscape case labels.

Reads:
  - data/clc_nbs_hazard.csv
  - data/landscapearchetype.csv

Writes:
  - data/clc_nbs_hazard_updated.csv

Harmonization:
  - strip whitespace on ``hazard`` / ``desc0`` / ``nbs_code``
  - map inconsistent hazard spellings to a single canonical label
    (e.g. ``Floods`` → ``Flood``)

Landscape case:
  - join on ``clc`` + ``desc0`` with landscapearchetype.csv
  - add column ``landscape_case`` from ``lac_d`` (Urban / Rural / Coastal / …)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

# Canonical NBS CSV hazard labels (values used after harmonization).
_HAZARD_CANONICAL: dict[str, str] = {
    'flood': 'Flood',
    'floods': 'Flood',
    'drought': 'Drought',
    'erosion': 'Erosion',
    'fires': 'Fires',
    'fire': 'Fires',
    'heat': 'Heat',
    'other': 'Other',
    'sea level rise': 'Sea level rise',
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _harmonize_hazard(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() == 'nan':
        return ''
    return _HAZARD_CANONICAL.get(text.lower(), text)


def harmonize_clc_nbs_hazard(
    nbs_path: Path,
    archetype_path: Path,
    out_path: Path,
) -> pd.DataFrame:
    nbs = pd.read_csv(nbs_path)
    arch = pd.read_csv(archetype_path, sep=';')

    for col in ('hazard', 'desc0', 'nbs_code'):
        if col in nbs.columns:
            nbs[col] = nbs[col].astype(str).str.strip()
            nbs.loc[nbs[col].str.lower() == 'nan', col] = ''

    nbs['hazard'] = nbs['hazard'].map(_harmonize_hazard)

    arch = arch.copy()
    arch['desc0'] = arch['desc0'].astype(str).str.strip()
    arch['lac_d'] = arch['lac_d'].astype(str).str.strip()
    arch.loc[arch['desc0'].str.lower() == 'nan', 'desc0'] = ''
    arch.loc[arch['lac_d'].str.lower().isin({'nan', ''}), 'lac_d'] = pd.NA

    # One lac_d per (clc, desc0); if duplicates disagree, keep first non-null.
    arch_key = (
        arch[['clc', 'desc0', 'lac_d']]
        .dropna(subset=['clc'])
        .drop_duplicates(subset=['clc', 'desc0'], keep='first')
    )

    merged = nbs.merge(arch_key, on=['clc', 'desc0'], how='left')
    merged = merged.rename(columns={'lac_d': 'landscape_case'})

    # Stable column order: original NBS cols + landscape_case.
    ordered = [c for c in nbs.columns if c in merged.columns] + ['landscape_case']
    merged = merged[ordered]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False)
    return merged


def main() -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--nbs',
        type=Path,
        default=root / 'data' / 'clc_nbs_hazard.csv',
        help='Input NBS mapping CSV',
    )
    parser.add_argument(
        '--archetype',
        type=Path,
        default=root / 'data' / 'landscapearchetype.csv',
        help='Landscape archetype CSV (semicolon-separated)',
    )
    parser.add_argument(
        '--out',
        type=Path,
        default=root / 'data' / 'clc_nbs_hazard_updated.csv',
        help='Output harmonized CSV',
    )
    args = parser.parse_args()

    if not args.nbs.is_file():
        raise SystemExit(f'NBS file not found: {args.nbs}')
    if not args.archetype.is_file():
        raise SystemExit(f'Archetype file not found: {args.archetype}')

    df = harmonize_clc_nbs_hazard(args.nbs, args.archetype, args.out)

    hazard_counts = df['hazard'].value_counts(dropna=False).to_dict()
    case_counts = df['landscape_case'].value_counts(dropna=False).to_dict()
    unmatched = int(df['landscape_case'].isna().sum())

    print(f'Wrote {len(df)} rows -> {args.out}')
    print(f'Hazards: {hazard_counts}')
    print(f'landscape_case: {case_counts}')
    print(f'Unmatched clc+desc0 (no landscape_case): {unmatched}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
