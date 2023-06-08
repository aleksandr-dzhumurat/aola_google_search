import json
import logging
import os
import requests
from typing import List, Dict

import openai

logging.basicConfig(format='%(asctime)s - %(name)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

openai.api_key = os.environ['OPENAI_API_KEY']

# YOBANYI STYD
search_result_f_name = '/srv/src/db.json'
if os.path.exists(search_result_f_name):
    with open(search_result_f_name, 'r') as f:
        global_cache = json.load(f)
else:
    global_cache = {}


def ids_to_candidates(candidates: dict, recs):
  res = []
  for i in recs:
    res.append(candidates.get(f'Response {i}'))
  return res

def extract_ids(input_string: str):
  import re

  ranked_responses = re.findall(r'\d+', input_string)
  ranked_responses = [int(response) for response in ranked_responses]
  return ranked_responses

def rank_candidates(user_onboarding: dict, candidates: dict):
  num_responces = len(candidates)
  promt = f"""
  Given a JSON file that contains an instruction and {num_responces} potential responses,
  please rank the quality of these responses, and return the index of the ranked responses,
  no additional explanation is needed. Put all ranked responces in one row
  Ranked responses list: 
  """

  candidates.update(user_onboarding)
  response = openai.ChatCompletion.create(
      model="gpt-3.5-turbo",
      messages=[
              {"role": "system", "content": promt},
              {"role": "user", "content": json.dumps(candidates)},
          ]
  )
  logger.info('Requesting OpenAI...')

  result = ''
  for choice in response.choices:
      result += choice.message.content

  logger.info('OpenAI responce: %s', result)
  hope_this_is_ranks = result.split('\n')[-1]

  recs_ids = extract_ids(hope_this_is_ranks)

  return recs_ids


def get_google_response(query, limit: int):
  if query in global_cache.keys():
    # IMPORTANT: use cache to avoid extra-charges
    logging.info('Using cache for %s', query)
    google_result = global_cache[query]
  else:
    from serpapi import GoogleSearch
    
    GOOGLE_SEARCH_API_KEY = os.environ['GOOGLE_SEARCH_API_KEY']
    search = GoogleSearch({
        "q": query, 
        "location": "New York, New York, United States",
        "api_key": GOOGLE_SEARCH_API_KEY
      })
    google_result = search.get_dict()
    google_result = google_result['organic_results']
    global_cache[query] = google_result
    with open(search_result_f_name, 'w') as f:
        json.dump(global_cache, f)
    logger.info('search results saved to cache')
  return google_result[:limit]

def get_plain_txt_from_google(item):
  res = ''.join((
      item.get('snippet', ''),
      item['title'],
      ' '.join(set(i.lower().strip() for i in item.get('snippet_highlighted_words', ''))),
      ' '.join([i['date'] for i in item.get('sitelinks', {}).get('list', '')]),
      ' '.join(item.get('rich_snippet', {}).get('bottom', {}).get('extensions', '')),
      item['about_this_result']['regions'][0]
  ))
  return res

def normalize_google_response(google_response):
  candidates_google = [
      {
        'link': google_response[i]['link'],
        'title': google_response[i]['title'],
        'txt': get_plain_txt_from_google(google_response[i]),
        'source': 'google',
      }
      for i in range(len(google_response))
  ]

  return candidates_google

def get_aola_response(query: str, limit: int):
  data = {
      "query": query,"city": "new-york",
      "activity_categories":["restaurant","bar","nightlife_and_bar","nightlife","sport","family","theatre","cinema","tour","concert","sightseeing","arts_and_culture","things_to_do"]
  }

  headers = {'x-key': '8fc7c11e90f8b0338b5b680823a2fd84e7ecf636c1e82249ace3639fb3f2f60f'}
  url = "https://ml.aola.dev/api/v1/search/"
  res = requests.post(url, json=data, headers=headers).json()['payload']

  return res[:limit]

def normalize_aola_response(aola_result: list):
  candidates_aola = [
      {
          'link': aola_result[i]['url'],
          'title': aola_result[i]['name'],
          'txt': aola_result[i]['tags'],
          'source': 'aola',
      }
      for i in range(len(aola_result))
  ]

  return candidates_aola

def get_content_by_id(content_ids, content_db):
  res = [
    {
        'source': content_db[i]['source'],
        'url': content_db[i]['link'],
        'title': content_db[i]['title']
    }
    for i in content_ids
  ]

  return res

def get_user_preferences(raw_query: str):
    onboarding_pattern = 'onboarding: '
    preferences = "i love jazz"
    for row in raw_query.split('\n'):
        if onboarding_pattern in row.lower():
            preferences = row.lower().replace(onboarding_pattern, '')
    return {"Instruction": preferences}

def get_query_results(query: str) -> List[Dict[str, str]]:
    user_onboarding = get_user_preferences(query)

    google_result = get_google_response(query, limit=5)
    candidates_google = normalize_google_response(google_result)

    aola_result = get_aola_response(query, limit=5)
    candidates_aola = normalize_aola_response(aola_result)

    union_cadidates_list = candidates_aola + candidates_google
    candidates = {
        f"Response {i}": union_cadidates_list[i]['txt']
        for i in range(len(union_cadidates_list))
    }

    rec_ids = rank_candidates(user_onboarding, candidates)
    recs = get_content_by_id(rec_ids, union_cadidates_list)
    return recs

def query_results(user_query: str):
    res = get_query_results(user_query)
    res = [
        (res[i]['url'], res[i]['title'], res[i]['source'])
        for i in range(len(res))
    ]

    return res