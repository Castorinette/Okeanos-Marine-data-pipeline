import json
import os
import requests

# Authors : Gourdette Beeverly
# File role : Enrich species data with wikipedia summary and image


def enrich_species(scientific_name):

  clean_scientific_name = scientific_name.strip().replace(" ", "_")
  url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean_scientific_name}"
  headers = {"User-Agent": "OkeanosDataPipeline"}

  try:
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
      data = response.json()
      orig_img = (data.get("originalimage") or {}).get("source")
      thumb_img = (data.get("thumbnail") or {}).get("source")

      return {
          "common_name": data.get("titles", {}).get("normalized", data.get("title")),
          "trivia": data.get("extract"),
          "image_url": orig_img or thumb_img,
      }
  except Exception as e:
    print(f"REQUEST ERROR - ENRICH_SPECIE")

  return {"common_name": None, "trivia": None, "image_url": None}


def fetch_specie_info(input_file: str = "data/raw/species.json"):

  if not os.path.exists(input_file):
    print(f"File {input_file} not found")
    return None

  with open(input_file, "r", encoding="utf-8") as f:
    species = json.load(f)

  for sp in species:
    name = (sp.get("scientific_name")
        or sp.get("scientificName")
        or sp.get("species"))
    
    if name:
      infos = enrich_species(name)
      sp.update(infos)

  output_file = "data/processed/enriched_species.json"

  with open(output_file, "w", encoding="utf-8") as f:
    json.dump(species, f, ensure_ascii=False, indent=2)

  return output_file

if __name__ == "__main__":
  fetch_specie_info()