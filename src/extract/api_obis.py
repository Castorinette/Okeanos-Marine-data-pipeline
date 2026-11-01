import requests
import json


# Authors : Gourdette Beeverly 
# File role : Fetching data from https://api.obis.org/.

 
def fetch_species_observations():

    # SPECIES
    url = "https://api.obis.org/v3/checklist"
    headers = {"User-Agent": "OkeanosDataPipeline"}

    params = {"scientificname": "Animalia", "size": 50}
    response = requests.get(url, params=params, headers=headers)

    # Status test
    if response.status_code == 200:
        data = response.json().get("results", [])
    else:
        print(f"ERROR ANIMALIA - Status: {response.status_code}")

    attributes = {"scientificName", "taxonID", "kingdom", "is_marine", "is_terrestrial", "class", "order", "records", "sst"}

    data_animalia = [
        {k: item.get(k) for k in attributes}
        for item in data
        if item.get("taxonRank") == "Species"
        and item.get("records", 0) >= 500
        and item.get("species") is not None
    ]

    params =  {"scientificname": "Plantae", "size": 50}
    response = requests.get(url, params=params, headers=headers)


    if response.status_code == 200:
        data = response.json().get("results", [])
    else:
        print(f"ERROR PLANTAE - Status: {response.status_code}")

    data_plantae = [
        {k: item.get(k) for k in attributes}
        for item in data
        if item.get("taxonRank") == "Species"
        and item.get("records", 0) >= 500
        and item.get("species") is not None
    ]

    species =  data_plantae + data_animalia

    # OBSERVATIONS - FACT TABLE

    observations = []
    attributes = {"observation_id", "decimalLatitude", "decimalLongitude", "eventDate",
                "country", "stateProvince", "basisOfRecord"}
    url = "https://api.obis.org/v3/occurrence"

    for d in species:
        taxonid = d["taxonID"]
        params = {"taxonid": taxonid, "size" : 10000, "fields" : ",".join(attributes)}
        

        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json().get("results", [])

            for item in data :
                observations.append({
                    "taxonID": taxonid,
                    **{k: item.get(k) for k in attributes},})

        else:
            print(f"ERROR OBSERVATIONS - Status: {response.status_code}")

    # Saving
    with open('data/raw/observations.json', 'w') as obs:
        json.dump(observations, obs)

    with open('data/raw/species.json', 'w') as spe:
        json.dump(species, spe)

    return 'data/raw/observations.json', 'data/raw/species.json'