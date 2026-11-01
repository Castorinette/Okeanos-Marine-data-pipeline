import geopandas as gpd
import pandas as pd


# Authors : Gourdette Beeverly 
# File role : Fetching Marine Ecoregion position 

def fetch_ecoregion():
    meow = gpd.read_file("data/raw/Marine_Ecoregions_of_the_World/data/commondata/data0/meow_ecos_expl_clipped_expl.shp")
    obs = pd.read_json("data/raw/observations.json")

    points = gpd.GeoDataFrame(
        obs, 
        geometry=gpd.points_from_xy(obs.decimalLongitude, obs.decimalLatitude),
        crs=4326)

    joined = gpd.sjoin(
        points,
        meow[["ECO_CODE", "geometry"]],
        how="left",
        predicate="within",)

    joined = joined[~joined.index.duplicated(keep="first")]
    obs["ecoregion_id"] = joined["ECO_CODE"].astype("Int64")


    # ECOREGION TABLE

    ecoregion = (
        meow[["ECO_CODE","ECOREGION","PROVINCE","REALM","Lat_Zone"]].rename(columns={
            "ECO_CODE": "ecoregion_id",
            "ECOREGION": "ecoregion_name",
            "PROVINCE": "province",
            "REALM": "realm_name",
            "Lat_Zone": "climate_zone",}).drop_duplicates("ecoregion_id"))

    ecoregion["ecoregion_id"] = ecoregion["ecoregion_id"].astype('Int64')

    # Saving
    obs.to_json("data/processed/enriched_observations.json", orient="records", force_ascii=False, indent=2)
    ecoregion.to_json("data/processed/ecoregion.json", orient="records", force_ascii=False, indent=2)

    return "data/processed/enriched_observations.json", "data/processed/ecoregion.json"