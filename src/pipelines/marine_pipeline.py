from src.extract.api_obis import fetch_species_observations
from src.transform.api_wiki import fetch_specie_info
from src.transform.eco_region_geo import fetch_ecoregion
from src.transform.duckdb_transform import run_duckdb_processing
import pandas as pd
def run_marine_pipeline():

    # Extract
    raw_obs, raw_spec = fetch_species_observations()

    # Transform
    spec = fetch_specie_info(raw_spec)
    obs, eco = fetch_ecoregion()

    # Dashboard
    run_duckdb_processing(input_dir="data/processed", output_dir="data/final")

    print("Okeanos pipeline end.")


if __name__ == "__main__":
    run_marine_pipeline()