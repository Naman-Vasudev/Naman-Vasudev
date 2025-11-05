import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time
import hashlib
from xml.sax.saxutils import escape as xml_escape

# ---------------------------- CONFIG ----------------------------
HEADERS = {'authorization': 'token ' + os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME']  # "Naman-Vasudev"

# profile fields (fill once here)
PROFILE = {
    'os_line': 'Windows 11',
    'ide_line': 'VSCode',
    'prog_langs': 'Python · C++ · TypeScript',
    'comp_langs': 'HTML · CSS · JavaScript',
    'real_langs': 'English · Hindi · Punjabi',
    'hobby_software': 'Software · Mathematics · AI',
    'hobby_hardware': 'Astronomy',
    'email_personal': 'naman24vasudev@gmail.com',
    'linkedin': 'linkedin.com/in/naman-vasudev-423461325/',
    'instagram': 'naman_s_land'
}

QUERY_COUNT = {'user_getter': 0, 'follower_getter': 0, 'graph_repos_stars': 0, 'recursive_loc': 0, 'loc_query': 0}

# ---------------------- BASIC UTILITIES --------------------------

def format_plural(unit):
    return 's' if unit != 1 else ''

def daily_readme(birthday):
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return f"{diff.years} year{format_plural(diff.years)}, {diff.months} month{format_plural(diff.months)}, {diff.days} day{format_plural(diff.days)}" + (" 🎂" if diff.months == 0 and diff.days == 0 else "")

def simple_request(func_name, query, variables):
    r = requests.post('https://api.github.com/graphql', json={'query': query, 'variables': variables}, headers=HEADERS)
    if r.status_code == 200:
        return r
    raise Exception(func_name, 'failed with', r.status_code, r.text)

# ---------------------- GRAPHQL FUNCTIONS ------------------------

def user_getter(username):
    QUERY_COUNT['user_getter'] += 1
    query = '''
    query($login: String!){
        user(login: $login) { id createdAt }
    }'''
    r = simple_request('user_getter', query, {'login': username})
    return {'id': r.json()['data']['user']['id']}, r.json()['data']['user']['createdAt']

def follower_getter(username):
    QUERY_COUNT['follower_getter'] += 1
    query = '''
    query($login: String!){
        user(login: $login) { followers { totalCount } }
    }'''
    r = simple_request('follower_getter', query, {'login': username})
    return int(r.json()['data']['user']['followers']['totalCount'])

def graph_repos_stars(count_type, owner_affiliation, cursor=None):
    QUERY_COUNT['graph_repos_stars'] += 1
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
      user(login: $login) {
        repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
          totalCount
          edges {
            node {
              nameWithOwner
              stargazers { totalCount }
            }
          }
          pageInfo { endCursor hasNextPage }
        }
      }
    }'''
    v = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    r = simple_request('graph_repos_stars', query, v)
    if count_type == 'repos':
        return r.json()['data']['user']['repositories']['totalCount']
    elif count_type == 'stars':
        return sum(n['node']['stargazers']['totalCount'] for n in r.json()['data']['user']['repositories']['edges'])

# -------------------------- SVG HELPERS --------------------------

def find_and_replace(root, element_id, new_text):
    el = root.find(f".//*[@id='{element_id}']")
    if el is not None:
        el.text = str(new_text)

def justify_format(root, element_id, new_text, length=0):
    if isinstance(new_text, int):
        new_text = f"{new_text:,}"
    find_and_replace(root, element_id, str(new_text))

def insert_ascii(root, group_id, ascii_text, line_height=12):
    group = root.find(f".//*[@id='{group_id}']")
    if group is None:
        return
    for c in list(group):
        group.remove(c)
    text_el = etree.Element("text", attrib={"xml:space": "preserve", "class": "mono", "x": "0", "y": "0"})
    lines = ascii_text.splitlines()
    for i, line in enumerate(lines):
        t = etree.Element("tspan", attrib={"x": "0", "dy": str(line_height if i > 0 else 0)})
        t.text = xml_escape(line)
        text_el.append(t)
    group.append(text_el)

def svg_overwrite(filename, age_data, commit_data, star_data, repo_data, follower_data):
    tree = etree.parse(filename)
    root = tree.getroot()

    # fill textual fields
    for key, value in PROFILE.items():
        find_and_replace(root, key, value)

    # numeric fields
    justify_format(root, 'commit_data', commit_data)
    justify_format(root, 'star_data', star_data)
    justify_format(root, 'repo_data', repo_data)
    justify_format(root, 'follower_data', follower_data)
    justify_format(root, 'loc_data', 0)
    justify_format(root, 'loc_add', 0)
    justify_format(root, 'loc_del', 0)

    # ASCII art insertion
    try:
        with open('ascii-art.txt', 'r', encoding='utf-8') as f:
            art = f.read()
        insert_ascii(root, 'ascii_group', art, line_height=12)
    except Exception as e:
        print('⚠️ ASCII art insertion failed:', e)

    tree.write(filename, encoding='utf-8', xml_declaration=True)

# --------------------------- MAIN LOGIC --------------------------

if __name__ == '__main__':
    print("Updating SVG with GitHub data...")

    user_data, _ = user_getter(USER_NAME)
    commit_data = 0  # commit counter can be added later if needed
    star_data = graph_repos_stars('stars', ['OWNER'])
    repo_data = graph_repos_stars('repos', ['OWNER'])
    follower_data = follower_getter(USER_NAME)
    age = daily_readme(datetime.datetime(2006, 10, 24))

    svg_overwrite('light_mode.svg', age, commit_data, star_data, repo_data, follower_data)

    print(f"Done. Stars: {star_data}, Repos: {repo_data}, Followers: {follower_data}")
