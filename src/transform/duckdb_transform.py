import os
import duckdb


def run_duckdb_processing(
    input_dir: str = "data/processed", output_dir: str = "data/final"):
  os.makedirs(output_dir, exist_ok=True)
  con = duckdb.connect()


# Fact table
  obs_file = (
      f"{input_dir}/enriched_observations.json"
      if os.path.exists(f"{input_dir}/enriched_observations.json")
      else f"{input_dir}/observations.json")


  con.execute(f"""
        CREATE OR REPLACE VIEW cleaned_observations AS
        WITH raw AS (
            SELECT 
                row_number() OVER () AS observation_id,
                CAST(taxonID AS INT) AS specie_id,
                COALESCE(CAST(ecoregion_id AS INT), 0) AS ecoregion_id,
                decimalLatitude,
                decimalLongitude,
                country AS country_code,
                stateProvince AS state_province,
                basisOfRecord,
                split_part(eventDate, '/', 1) AS date_candidate
            FROM read_json_auto('{obs_file}')
            WHERE eventDate IS NOT NULL)

        SELECT *,
            CASE 
                WHEN length(date_candidate) >= 10 THEN TRY_CAST(substring(date_candidate, 1, 10) AS DATE)
                WHEN length(date_candidate) = 4 THEN TRY_CAST(date_candidate || '-01-01' AS DATE)
                ELSE NULL 
            END AS parsed_date
        FROM raw
    """)

  # Export de fact_marine_observations.parquet
  con.execute(f"""
        COPY (
            SELECT 
                observation_id,
                specie_id,
                CAST(strftime(parsed_date, '%Y%m%d') AS INT) AS date_id,
                ecoregion_id,
                decimalLatitude,
                decimalLongitude,
                country_code,
                state_province,
                basisOfRecord
            FROM cleaned_observations
            WHERE parsed_date IS NOT NULL
        ) TO '{output_dir}/fact_marine_observations.parquet' (FORMAT PARQUET)
    """)

  # Date dimension
  con.execute(f"""
        COPY (
            SELECT DISTINCT
                CAST(strftime(parsed_date, '%Y%m%d') AS INT) AS date_id,
                strftime(parsed_date, '%Y-%m-%d') AS full_date,
                EXTRACT(YEAR FROM parsed_date) AS year,
                CAST(EXTRACT(YEAR FROM parsed_date) AS VARCHAR) AS year_name,
                EXTRACT(MONTH FROM parsed_date) AS month,
                strftime(parsed_date, '%B') AS month_name,
                EXTRACT(DAY FROM parsed_date) AS day,
                strftime(parsed_date, '%A') AS day_name,
                CASE 
                    WHEN EXTRACT(MONTH FROM parsed_date) IN (12, 1, 2) THEN 'Winter'
                    WHEN EXTRACT(MONTH FROM parsed_date) IN (3, 4, 5) THEN 'Spring'
                    WHEN EXTRACT(MONTH FROM parsed_date) IN (6, 7, 8) THEN 'Summer'
                    ELSE 'Autumn'
                END AS season
            FROM cleaned_observations
            WHERE parsed_date IS NOT NULL
            ORDER BY date_id
        ) TO '{output_dir}/dim_date.parquet' (FORMAT PARQUET)
    """)

  # Dimension specie
  species_file = (
      f"{input_dir}/enriched_species.json"
      if os.path.exists(f"{input_dir}/enriched_species.json")
      else f"{input_dir}/species.json"
  )

  con.execute(f"""
        COPY (
            SELECT DISTINCT
                CAST(taxonID AS INT) AS specie_id,
                scientificName AS scientific_name,
                common_name,
                kingdom,
                class,
                "order",
                trivia,
                image_url,
                records AS total_records
            FROM read_json_auto('{species_file}')
            WHERE taxonID IS NOT NULL
        ) TO '{output_dir}/dim_species.parquet' (FORMAT PARQUET) """)

  # Ecoregion dimensions
  con.execute(f"""
        COPY (
            SELECT DISTINCT
                CAST(ecoregion_id AS INT) AS ecoregion_id,
                ecoregion_name,
                province,
                realm_name,
                climate_zone
            FROM read_json_auto('{input_dir}/ecoregion.json')
            WHERE ecoregion_id IS NOT NULL
        ) TO '{output_dir}/dim_ecoregion.parquet' (FORMAT PARQUET)
    """)

  con.close()
  print("🦆 Couche Gold générée avec succès dans data/final/ !")


if __name__ == "__main__":
  run_duckdb_processing()