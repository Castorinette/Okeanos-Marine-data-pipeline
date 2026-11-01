import json
import os
import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

st.set_page_config(
    page_title="Okeanos — Marine Biology Explorer",
    page_icon="🌊",
    layout="wide",
)

st.title("🌊 Okeanos — Marine Biology Explorer")

DATA_DIR = "data/final"
GEOJSON_PATH = "data/processed/ecoregions.geojson"
MAX_POINTS = 30000


# Load tables
def read_pq(name):
  path = f"{DATA_DIR}/{name}"
  if os.path.exists(f"{path}.parquet"):
    return pd.read_parquet(f"{path}.parquet")
  elif os.path.exists(path):
    return pd.read_parquet(path)
  raise FileNotFoundError(f"Table not found: {path}")


@st.cache_data(show_spinner="Loading data from Gold Layer...")
def load_data():
  fact = read_pq("fact_marine_observations")
  species = read_pq("dim_species")
  eco = read_pq("dim_ecoregion")
  date = read_pq("dim_date")

  valid_species_ids = fact["specie_id"].unique()
  species = species[species["specie_id"].isin(valid_species_ids)].copy()

  # Standardize scientific name column
  if "scientificName" in species.columns and "scientific_name" not in species:
    species = species.rename(columns={"scientificName": "scientific_name"})

  # Standardize foreign keys
  fact["specie_id"] = (
      pd.to_numeric(fact["specie_id"], errors="coerce").fillna(-1).astype(int)
  )
  species["specie_id"] = (
      pd.to_numeric(species["specie_id"], errors="coerce")
      .fillna(-1)
      .astype(int)
  )

  if "ecoregion_id" in fact.columns:
    fact["ecoregion_id"] = (
        pd.to_numeric(fact["ecoregion_id"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

  # Derive calendar year
  if "date_id" in fact.columns:
    if "date_id" in date.columns and "year" in date.columns:
      date_map = (
          date[["date_id", "year"]]
          .drop_duplicates("date_id")
          .set_index("date_id")
      )
      fact["year"] = fact["date_id"].map(date_map["year"])
    fact["year"] = (
        fact["year"].fillna(fact["date_id"] // 10000).fillna(0).astype(int)
    )

  # Attach MEOW ecoregion labels
  if "ecoregion_id" in eco.columns:
    eco["ecoregion_id"] = (
        pd.to_numeric(eco["ecoregion_id"], errors="coerce")
        .fillna(0)
        .astype(int)
    )
    eco_map = (
        eco[["ecoregion_id", "ecoregion_name", "province", "realm_name"]]
        .drop_duplicates("ecoregion_id")
        .set_index("ecoregion_id")
    )
    fact["ecoregion_name"] = fact["ecoregion_id"].map(
        eco_map["ecoregion_name"]
    )
    fact["province"] = fact["ecoregion_id"].map(eco_map["province"])
    fact["realm_name"] = fact["ecoregion_id"].map(eco_map["realm_name"])

  fact["ecoregion_name"] = fact["ecoregion_name"].fillna(
      "High Seas / Unassigned"
  )

  return fact, species, eco


@st.cache_data
def load_geojson():
  for candidate in [GEOJSON_PATH, "data/processed/ecoregion_geo.geojson"]:
    if os.path.exists(candidate):
      try:
        with open(candidate, "r", encoding="utf-8") as f:
          return json.load(f)
      except Exception:
        pass
  return None


fact_df, dim_species, dim_ecoregion = load_data()
geo_data = load_geojson()

# Sidebars filter
st.sidebar.header("Filters")

#Kingdom
kingdoms = ["All"] + sorted(dim_species["kingdom"].dropna().unique().tolist())
selected_kingdom = st.sidebar.selectbox("Kingdom", kingdoms)

species_pool = dim_species.copy()
if selected_kingdom != "All":
  species_pool = species_pool[species_pool["kingdom"] == selected_kingdom]

#  Species 
species_options = ["All"] + sorted(
    species_pool["scientific_name"].dropna().unique().tolist()
)
selected_species = st.sidebar.selectbox(
    "Species (Scientific Name)", species_options
)

# MEOW 
eco_real = dim_ecoregion[dim_ecoregion["ecoregion_id"] != 0]
eco_options = ["All"] + sorted(
    eco_real["ecoregion_name"].dropna().unique().tolist()
)
selected_eco = st.sidebar.selectbox("Marine Ecoregion", eco_options)

# Data filtering
df_filtered = fact_df.copy()

if selected_kingdom != "All":
  valid_species = dim_species.loc[
      dim_species["kingdom"] == selected_kingdom, "specie_id"
  ]
  df_filtered = df_filtered[df_filtered["specie_id"].isin(valid_species)]

species_row = None
if selected_species != "All":
  species_row = dim_species[
      dim_species["scientific_name"] == selected_species
  ].iloc[0]
  target_id = int(species_row["specie_id"])
  df_filtered = df_filtered[df_filtered["specie_id"] == target_id]

if selected_eco != "All":
  df_filtered = df_filtered[df_filtered["ecoregion_name"] == selected_eco]

# Join with species metadata for labels and rendering
df_filtered = df_filtered.merge(
    dim_species[[
        "specie_id",
        "scientific_name",
        "common_name",
        "kingdom",
        "class",
    ]],
    on="specie_id",
    how="left",
)

# Marker color: Cyan (Animalia), Emerald (Plantae)
df_filtered["point_color"] = df_filtered["kingdom"].apply(
    lambda k: [0, 210, 255, 200] if k == "Animalia" else [46, 204, 113, 200]
)


kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric("Filtered Observations", f"{len(df_filtered):,}")
kpi2.metric(
    "Tracked Species",
    f"{df_filtered['specie_id'].nunique():,} / {dim_species['specie_id'].nunique():,}",
)
n_eco = df_filtered.loc[
    df_filtered["ecoregion_id"] != 0, "ecoregion_id"
].nunique()
kpi3.metric("Covered Ecoregions", f"{n_eco:,}")

st.markdown("---")

# Profile card
if species_row is not None:
  st.subheader(f"Species card: *{species_row['scientific_name']}*")
  col_img, col_desc = st.columns([1, 2])

  with col_img:
    img = species_row.get("image_url")
    if pd.notnull(img) and str(img).strip() != "":
      st.image(img, width="stretch")
    else:
      st.info("No image available.")

  with col_desc:
    st.markdown(
        f"**Common Name:** {species_row.get('common_name') or 'Not provided'}"
    )
    st.markdown(f"**Kingdom:** {species_row.get('kingdom', '-')}")
    st.markdown(f"**Class:** {species_row.get('class', '-')}")
    st.markdown(f"**Order:** {species_row.get('order', '-')}")
    if pd.notnull(species_row.get("trivia")):
      st.markdown(f"**Summary:** {species_row['trivia']}")

  st.markdown("---")

# Pydeck
st.subheader("Map")

layers = []

# A. MEOW Ecoregion Boundaries
if geo_data is not None:
  if selected_eco != "All":
    feats = [
        ft
        for ft in geo_data.get("features", [])
        if ft.get("properties", {}).get("ecoregion_name") == selected_eco
    ]
    fill_col = [0, 200, 180, 85]
    line_col = [0, 255, 220, 255]
  else:
    eco_ids_in_data = set(
        df_filtered.loc[df_filtered["ecoregion_id"] != 0, "ecoregion_id"]
        .dropna()
        .astype(int)
    )
    feats = [
        ft
        for ft in geo_data.get("features", [])
        if int(ft.get("properties", {}).get("ecoregion_id", -1))
        in eco_ids_in_data
    ]
    fill_col = [30, 144, 255, 30]
    line_col = [30, 144, 255, 120]

  if feats:
    layers.append(
        pdk.Layer(
            "GeoJsonLayer",
            data={"type": "FeatureCollection", "features": feats},
            pickable=True,
            stroked=True,
            filled=True,
            get_fill_color=fill_col,
            get_line_color=line_col,
            line_width_min_pixels=1,
        )
    )

# Specie occuerence scatterplot
if selected_species != "All":
  map_points = df_filtered.dropna(
      subset=["decimalLatitude", "decimalLongitude"]
  ).copy()

  if not map_points.empty:
    if len(map_points) > MAX_POINTS:
      map_points = map_points.sample(MAX_POINTS, random_state=42)

    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=map_points,
            get_position=["decimalLongitude", "decimalLatitude"],
            get_fill_color="point_color",
            get_radius=20000,
            radius_min_pixels=3,
            radius_max_pixels=8,
            pickable=True,
        )
    )
    center_lat = float(map_points["decimalLatitude"].mean())
    center_lon = float(map_points["decimalLongitude"].mean())
    zoom_val = 2.8
  else:
    st.warning("No GPS coordinates recorded for this species.")
    center_lat, center_lon, zoom_val = 20.0, 0.0, 1.2
else:
  st.info("**Select a species in the sidebar** to display its occurrences.")
  center_lat, center_lon, zoom_val = 20.0, 0.0, 1.2

tooltip_config = {
    "html": """
        <div style="font-family: sans-serif; font-size: 12px; color: white;">
            <b>Ecoregion:</b> {ecoregion_name}<br/>
            <!-- Si l'élément survolé est un point d'espèce -->
            <span style="display: {scientific_name ? 'inline' : 'none'};">
                <b>Species:</b> <i>{scientific_name}</i><br/>
                <b>Common:</b> {common_name}
            </span>
        </div>
    """,
    "style": {
        "backgroundColor": "#1e293b",
        "padding": "8px 12px",
        "borderRadius": "6px",
        "border": "1px solid #334155",
    },
}

st.pydeck_chart(
    pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=zoom_val,
            pitch=0,
        ),
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip=tooltip_config,
    )
)


st.markdown("---")

# Analytics
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
  st.subheader("Top 10 marine ecoregions")
  eco_counts = (
      df_filtered[df_filtered["ecoregion_name"] != "High Seas / Unassigned"]
      .groupby("ecoregion_name")["specie_id"]
      .count()
      .reset_index(name="record_count")
      .sort_values("record_count", ascending=False)
      .head(10)
  )

  if not eco_counts.empty:
    fig_eco = px.bar(
        eco_counts,
        x="record_count",
        y="ecoregion_name",
        orientation="h",
        title="Most Recorded Marine Ecoregions",
        labels={
            "record_count": "Observations",
            "ecoregion_name": "Marine Ecoregion",
        },
        color_discrete_sequence=["#00D2FF"],
    )
    fig_eco.update_layout(
        template="plotly_dark",
        yaxis={"categoryorder": "total ascending"},
        margin=dict(l=0, r=20, t=40, b=20),
    )
    st.plotly_chart(fig_eco, width="stretch")
  else:
    st.info("No ecoregion covered for the current selection.")

with col_chart2:
  st.subheader("Observations Timeline")
  if "year" in df_filtered.columns:
    chart_data = df_filtered[
        (df_filtered["year"] >= 1950) & (df_filtered["year"] <= 2026)
    ]
    yearly_counts = (
        chart_data.groupby("year")["specie_id"]
        .count()
        .reset_index(name="record_count")
        .sort_values("year")
    )

    if not yearly_counts.empty:
      fig_timeline = px.bar(
          yearly_counts,
          x="year",
          y="record_count",
          title="Observations Evolution per Year",
          labels={"year": "Year", "record_count": "Observations"},
          color_discrete_sequence=["#2ECC71"],
      )
      fig_timeline.update_layout(
          template="plotly_dark",
          bargap=0.2,
          margin=dict(l=0, r=20, t=40, b=20),
      )
      st.plotly_chart(fig_timeline, width="stretch")
    else:
      st.info("No temporal records available.")