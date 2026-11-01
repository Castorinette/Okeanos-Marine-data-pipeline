import json
import os
import random
import duckdb
import pandas as pd
import requests

from src.transform.api_wiki import enrich_species

# Author : Gourdette Beeverly
# Role : Daily enricher, add new specie to existing databases

DATA_FINAL_DIR = "data/final"
HEADERS = {"User-Agent": "OkeanosDataPipeline"}


def get_existing_species_ids():
  species_path = f"{DATA_FINAL_DIR}/dim_species.parquet"
  if os.path.exists(species_path):
    df = pd.read_parquet(species_path)
    return set(df["specie_id"].dropna().astype(int).tolist())
  return set()


def fetch_unseen_candidates(group, existing_ids, limit):
  url = "https://api.obis.org/v3/checklist"
  params = {"scientificname": group, "size": 300}
  res = requests.get(url, params=params, headers=HEADERS, timeout=20)

  if res.status_code != 200:
    return []

  results = res.json().get("results", [])
  candidates = []

  for item in results:
    t_id = item.get("taxonID")
    if (
        item.get("taxonRank") == "Species"
        and item.get("records", 0) >= 100
        and t_id is not None
        and int(t_id) not in existing_ids
    ):
      candidates.append({
          "specie_id": int(t_id),
          "scientific_name": item.get("species") or item.get("scientificName"),
          "kingdom": item.get("kingdom"),
          "class": item.get("class"),
          "order": item.get("order"),
          "total_records": item.get("records", 0),
      })

  return random.sample(candidates, min(len(candidates), limit))


def fetch_occurrences_species(taxon_id, max_records=500):
  url = "https://api.obis.org/v3/occurrence"
  params = {"taxonid": taxon_id, "size": max_records}
  res = requests.get(url, params=params, headers=HEADERS, timeout=30)

  if res.status_code != 200:
    return []

  data = res.json().get("results", [])
  valid_points = []
  for item in data:
    if (
        item.get("decimalLatitude") is not None
        and item.get("decimalLongitude") is not None
        and item.get("eventDate") is not None
    ):
      valid_points.append({
          "specie_id": taxon_id,
          "decimalLatitude": float(item["decimalLatitude"]),
          "decimalLongitude": float(item["decimalLongitude"]),
          "eventDate": str(item["eventDate"]),
          "country_code": item.get("country"),
          "state_province": item.get("stateProvince"),
          "basisOfRecord": item.get("basisOfRecord"),
      })

  return valid_points


def run_daily(batch_size: int = 5):
  existing_ids = get_existing_species_ids()
  n_animals = batch_size // 2 + 1
  n_plants = batch_size - n_animals

  new_species = fetch_unseen_candidates(
      "Animalia", existing_ids, limit=n_animals
  )
  new_species += fetch_unseen_candidates("Plantae", existing_ids, limit=n_plants)

  if not new_species:
    print("No new species")
    return

  print(f"{len(new_species)} new species today :")
  for sp in new_species:
    print(f"   • {sp['scientific_name']} ({sp['kingdom']})")

  all_new_obs = []
  for sp in new_species:
    # Wikipédia
    wiki_info = enrich_species(sp["scientific_name"])
    sp["common_name"] = wiki_info.get("common_name")
    sp["trivia"] = wiki_info.get("trivia")
    sp["image_url"] = wiki_info.get("image_url")

    obs = fetch_occurrences_species(sp["specie_id"])
    all_new_obs.extend(obs)

  con = duckdb.connect()

  # MAJ Specie
  df_new_species = pd.DataFrame(new_species)
  df_new_species["added_at"] = pd.Timestamp.now().strftime("%Y-%m-%d")
  con.register("new_species_df", df_new_species)


  existing_cols = [
      col[0]
      for col in con.execute(
          f"DESCRIBE SELECT * FROM '{DATA_FINAL_DIR}/dim_species.parquet'").fetchall()]
  added_at_expr = (
      "added_at"
      if "added_at" in existing_cols
      else "'2026-11-01' AS added_at"
  )

  con.execute(f"""
        COPY (
            SELECT 
                specie_id,
                scientific_name,
                common_name,
                kingdom,
                class,
                "order",
                trivia,
                image_url,
                total_records,
                {added_at_expr}
            FROM '{DATA_FINAL_DIR}/dim_species.parquet'
            UNION ALL
            SELECT 
                specie_id,
                scientific_name,
                common_name,
                kingdom,
                class,
                "order",
                trivia,
                image_url,
                total_records,
                added_at
            FROM new_species_df
        ) TO '{DATA_FINAL_DIR}/dim_species.parquet' (FORMAT PARQUET)
    """)
  # MAJ observation
  if all_new_obs:
    df_new_obs = pd.DataFrame(all_new_obs)

    res = con.cursor().execute(
        f"SELECT COALESCE(MAX(observation_id), 0) FROM"
        f" '{DATA_FINAL_DIR}/fact_marine_observations.parquet'"
    ).fetchall()
    current_max_id = int(res[0][0]) if res else 0

    df_new_obs["observation_id"] = range(current_max_id + 1, current_max_id + 1 + len(df_new_obs))
    df_new_obs["ecoregion_id"] = 0
    df_new_obs["date_candidate"] = df_new_obs["eventDate"].apply(lambda d: str(d).split("/")[0] if pd.notnull(d) else "2020-01-01")

    # Saving
    con.register("new_obs_df", df_new_obs)

    con.execute(f"""
            COPY (
                SELECT 
                    observation_id,
                    specie_id,
                    date_id,
                    ecoregion_id,
                    decimalLatitude,
                    decimalLongitude,
                    country_code,
                    state_province,
                    basisOfRecord
                FROM '{DATA_FINAL_DIR}/fact_marine_observations.parquet'
                UNION ALL
                SELECT 
                    observation_id,
                    specie_id,
                    CAST(strftime(TRY_CAST(substring(date_candidate, 1, 10) AS DATE), '%Y%m%d') AS INT) AS date_id,
                    ecoregion_id,
                    decimalLatitude,
                    decimalLongitude,
                    country_code,
                    state_province,
                    basisOfRecord
                FROM new_obs_df
                WHERE TRY_CAST(substring(date_candidate, 1, 10) AS DATE) IS NOT NULL
            ) TO '{DATA_FINAL_DIR}/fact_marine_observations.parquet' (FORMAT PARQUET)
        """)

  con.close()


if __name__ == "__main__":
  run_daily(batch_size=5)