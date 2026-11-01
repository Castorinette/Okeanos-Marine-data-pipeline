import geopandas as gpd


gdf = gpd.read_file('data/raw/Marine_Ecoregions_of_the_World/data/commondata/data0/meow_ecos_expl_clipped_expl.shp')
gdf = gdf.to_crs(4326)[['ECO_CODE', 'ECOREGION', 'REALM', 'geometry']]
gdf = gdf.rename(columns={'ECO_CODE': 'ecoregion_id', 'ECOREGION': 'ecoregion_name', 'REALM': 'realm_name'})
gdf['ecoregion_id'] = gdf['ecoregion_id'].astype(int)
gdf['geometry'] = gdf['geometry'].simplify(0.05, preserve_topology=True)
gdf.to_file('data/processed/ecoregions.geojson', driver='GeoJSON')
