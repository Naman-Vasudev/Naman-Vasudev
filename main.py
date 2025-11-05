#!/usr/bin/env python3
# main.py - dynamic GitHub profile card generator (Andrew-style), adapted for Naman Vasudev
import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time
import hashlib
import sys

# --- Configuration / Profile (some are fetched dynamically via API) ---
# These are your static profile lines used in the SVG text fields.
PROFILE = {
    "display_name": "Naman Vasudev",
    "os_line": "Windows 11",
    "uptime_line": "",   # optional, left blank (could be used later)
    "host_line": "",     # optional
    "kernel_line": "",   # optional
    "ide_line": "VSCode",
    "prog_langs": "Python, C++, TypeScript",
    "comp_langs": "HTML, CSS, JavaScript",
    "real_langs": "English, Hindi, Punjabi",
    "hobby_software": "Software, Mathematics, AI",
    "hobby_hardware": "Astronomy",   # inserted per your request
    "email_personal": "naman24vasudev@gmail.com",
    "linkedin": "https://www.linkedin.com/in/naman-vasudev-423461325/",
    "instagram": "naman_s_land",
    "accent_color": "#FF007F",  # default; you can change
}

# GitHub GraphQL HEADERS using repository secret ACCESS_TOKEN and USER_NAME
try:
    HEADERS = {'authorization': 'token ' + os.environ['ACCESS_TOKEN']}
    USER_NAME = os.environ['USER_NAME']
except KeyError as e:
    print("Missing environment variable:", e)
    sys.exit(1)

# Query counters for debugging/diagnostics
QUERY_COUNT = {'user_getter': 0, 'follower_getter': 0, 'graph_repos_stars': 0,
               'recursive_loc': 0, 'graph_commits': 0, 'loc_query': 0}

# --- Utility functions ---------------------------------------------------

def format_plural(unit):
    return 's' if unit != 1 else ''

def daily_readme(birthday):
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}{}, {} {}{}, {} {}{}'.format(
        diff.years, 'year', format_plural(diff.years) and '' or '', '',
        diff.months, 'month' + format_plural(diff.months),
        diff.days, 'day' + format_plural(diff.days),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else ''
    )

def simple_request(func_name, query, variables):
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables': variables}, headers=HEADERS)
    if request.status_code == 200:
        return request
    raise Exception(func_name + " failed", request.status_code, request.text)

def query_count(funct_id):
    global QUERY_COUNT
    QUERY_COUNT[funct_id] += 1

# --- GraphQL helpers -----------------------------------------------------

def user_getter(username):
    query_count('user_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            id
            createdAt
            name
            login
        }
    }'''
    variables = {'login': username}
    request = simple_request('user_getter', query, variables)
    data = request.json()['data']['user']
    return {'id': data['id']}, data['createdAt']

def follower_getter(username):
    query_count('follower_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            followers { totalCount }
        }
    }'''
    req = simple_request('follower_getter', query, {'login': username})
    return int(req.json()['data']['user']['followers']['totalCount'])

def graph_repos_stars(count_type, owner_affiliation, cursor=None):
    query_count('graph_repos_stars')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers { totalCount }
                            defaultBranchRef {
                                target {
                                    ... on Commit {
                                        history { totalCount }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo { endCursor hasNextPage }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request('graph_repos_stars', query, variables)
    jsondata = request.json()['data']['user']['repositories']
    if count_type == 'repos':
        return jsondata['totalCount']
    elif count_type == 'stars':
        return stars_counter(jsondata['edges'])
    elif count_type == 'repos_edges':
        return jsondata['edges'], jsondata['pageInfo']

def stars_counter(edges):
    total = 0
    for node in edges:
        total += node['node']['stargazers']['totalCount']
    return total

# --- LOC counting (cache-based) -----------------------------------------

def recursive_loc(owner, repo_name, data, cache_comment, addition_total=0, deletion_total=0, my_commits=0, cursor=None):
    query_count('recursive_loc')
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    ... on Commit {
                                        committedDate
                                    }
                                    author { user { id } }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo { endCursor hasNextPage }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor}
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables': variables}, headers=HEADERS)
    if request.status_code != 200:
        force_close_file(data, cache_comment)
        if request.status_code == 403:
            raise Exception('Rate limit / abuse detected')
        raise Exception('recursive_loc() failed', request.status_code, request.text)

    repo_data = request.json()['data']['repository']
    if repo_data and repo_data.get('defaultBranchRef') is not None:
        history = repo_data['defaultBranchRef']['target']['history']
        return loc_counter_one_repo(owner, repo_name, data, cache_comment, history, addition_total, deletion_total, my_commits)
    return 0

def loc_counter_one_repo(owner, repo_name, data, cache_comment, history, addition_total, deletion_total, my_commits):
    for node in history['edges']:
        if node['node']['author'] and node['node']['author'].get('user') and node['node']['author']['user'].get('id') == OWNER_ID:
            my_commits += 1
            addition_total += node['node'].get('additions', 0)
            deletion_total += node['node'].get('deletions', 0)
    if history['edges'] == [] or not history['pageInfo']['hasNextPage']:
        return addition_total, deletion_total, my_commits
    else:
        return recursive_loc(owner, repo_name, data, cache_comment, addition_total, deletion_total, my_commits, history['pageInfo']['endCursor'])

def loc_query(owner_affiliation, comment_size=0, force_cache=False, cursor=None, edges=None):
    if edges is None: edges = []
    query_count('loc_query')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            defaultBranchRef {
                                target {
                                    ... on Commit {
                                        history { totalCount }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo { endCursor hasNextPage }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request('loc_query', query, variables)
    repo_json = request.json()['data']['user']['repositories']
    edges += repo_json['edges']
    if repo_json['pageInfo']['hasNextPage']:
        return loc_query(owner_affiliation, comment_size, force_cache, repo_json['pageInfo']['endCursor'], edges)
    return cache_builder(edges, comment_size, force_cache)

def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    cached = True
    filename = 'cache/' + hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt'
    try:
        with open(filename, 'r') as f:
            data = f.readlines()
    except FileNotFoundError:
        data = []
        if comment_size > 0:
            for _ in range(comment_size): data.append('This is a comment line for the cache file.\n')
        with open(filename, 'w') as f:
            f.writelines(data)
    if len(data) - comment_size != len(edges) or force_cache:
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, 'r') as f: data = f.readlines()
    cache_comment = data[:comment_size]
    data = data[comment_size:]
    # ensure data matches length
    if len(data) < len(edges):
        # rebuild minimal structure
        flush_cache(edges, filename, comment_size)
        with open(filename, 'r') as f: data = f.readlines()[comment_size:]
    for index in range(len(edges)):
        repo_hash = hashlib.sha256(edges[index]['node']['nameWithOwner'].encode('utf-8')).hexdigest()
        try:
            line = data[index].split()
            old_hash = line[0]
            commit_count = int(line[1])
        except Exception:
            # new file or malformed line: force recalc
            commit_count = -1
            old_hash = ''
        # if commit_count not match, update via recursive_loc
        try:
            current_count = edges[index]['node']['defaultBranchRef']['target']['history']['totalCount']
        except Exception:
            current_count = 0
        if old_hash != repo_hash or commit_count != current_count:
            owner, repo_name = edges[index]['node']['nameWithOwner'].split('/')
            loc = recursive_loc(owner, repo_name, data, cache_comment)
            line_str = f"{repo_hash} {current_count} {loc[2]} {loc[0]} {loc[1]}\n"
            data[index] = line_str
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    for line in data:
        parts = line.split()
        if len(parts) >= 5:
            loc_add += int(parts[3])
            loc_del += int(parts[4])
    return [loc_add, loc_del, loc_add - loc_del, cached]

def flush_cache(edges, filename, comment_size):
    try:
        with open(filename, 'r') as f:
            comment = f.readlines()[:comment_size] if comment_size > 0 else []
    except FileNotFoundError:
        comment = []
    with open(filename, 'w') as f:
        f.writelines(comment)
        for node in edges:
            f.write(hashlib.sha256(node['node']['nameWithOwner'].encode('utf-8')).hexdigest() + ' 0 0 0 0\n')

def add_archive():
    try:
        with open('cache/repository_archive.txt', 'r') as f:
            data = f.readlines()
    except FileNotFoundError:
        return [0,0,0,0,0]
    old_data = data
    data = data[7:len(data)-3] if len(data) > 10 else []
    added_loc = deleted_loc = added_commits = 0
    contributed_repos = len(data)
    for line in data:
        parts = line.split()
        if len(parts) >= 5:
            added_loc += int(parts[3])
            deleted_loc += int(parts[4])
            if parts[2].isdigit():
                added_commits += int(parts[2])
    if old_data:
        try:
            added_commits += int(old_data[-1].split()[4][:-1])
        except Exception:
            pass
    return [added_loc, deleted_loc, added_loc - deleted_loc, added_commits, contributed_repos]

def force_close_file(data, cache_comment):
    filename = 'cache/'+hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    print('Error while writing cache: partial saved to', filename)

def commit_counter(comment_size):
    total_commits = 0
    filename = 'cache/'+hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest()+'.txt'
    with open(filename, 'r') as f:
        data = f.readlines()
    data = data[comment_size:]
    for line in data:
        parts = line.split()
        if len(parts) >= 3:
            total_commits += int(parts[2])
    return total_commits

# --- SVG manipulation ---------------------------------------------------

def find_and_replace(root, element_id, new_text):
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        # preserve whitespace
        element.text = str(new_text)

def justify_format(root, element_id, new_text, length=0):
    if isinstance(new_text, int):
        new_text = f"{new_text:,}"
    new_text = str(new_text)
    find_and_replace(root, element_id, new_text)
    just_len = max(0, length - len(new_text))
    if just_len <= 2:
        dot_map = {0: '', 1: ' ', 2: '. '}
        dot_string = dot_map[just_len]
    else:
        dot_string = ' ' + ('.' * just_len) + ' '
    find_and_replace(root, f"{element_id}_dots", dot_string)

def svg_overwrite(filename, age_data, commit_data, star_data, repo_data, contrib_data, follower_data, loc_data):
    tree = etree.parse(filename)
    root = tree.getroot()
    # numeric/stats fields (IDs must exist in SVG)
    justify_format(root, 'commit_data', commit_data, 22)
    justify_format(root, 'commit_data_dots', '', 0)
    justify_format(root, 'star_data', star_data, 14)
    justify_format(root, 'star_data_dots', '', 0)
    justify_format(root, 'repo_data', repo_data, 6)
    justify_format(root, 'repo_data_dots', '', 0)
    justify_format(root, 'contrib_data', contrib_data, 8)
    justify_format(root, 'contrib_data_dots', '', 0)
    justify_format(root, 'follower_data', follower_data, 10)
    justify_format(root, 'follower_data_dots', '', 0)
    justify_format(root, 'loc_data', loc_data[2], 9)
    justify_format(root, 'loc_data_dots', '', 0)
    justify_format(root, 'loc_add', loc_data[0])
    justify_format(root, 'loc_del', loc_data[1])
    # textual profile fields
    find_and_replace(root, 'os_line', PROFILE['os_line'])
    find_and_replace(root, 'ide_line', PROFILE['ide_line'])
    find_and_replace(root, 'prog_langs', PROFILE['prog_langs'])
    find_and_replace(root, 'comp_langs', PROFILE['comp_langs'])
    find_and_replace(root, 'real_langs', PROFILE['real_langs'])
    find_and_replace(root, 'hobby_software', PROFILE['hobby_software'])
    find_and_replace(root, 'hobby_hardware', PROFILE['hobby_hardware'])
    find_and_replace(root, 'email_personal', PROFILE['email_personal'])
    find_and_replace(root, 'linkedin', PROFILE['linkedin'])
    find_and_replace(root, 'instagram', PROFILE['instagram'])
    # ascii art (reads ascii-art.txt and puts raw text into element 'ascii_art')
    try:
        with open('ascii-art.txt', 'r', encoding='utf-8') as af:
            art = af.read()
        find_and_replace(root, 'ascii_art', art)
    except Exception:
        pass
    tree.write(filename, encoding='utf-8', xml_declaration=True)

# --- Main runner --------------------------------------------------------

if __name__ == '__main__':
    # Birthday (use the one you provided)
    birthday = datetime.datetime(2006, 10, 24)

    print("Starting profile card generation...")

    # 1) user data
    user_return, user_time = (user_getter(USER_NAME), 0.0) if False else (user_getter(USER_NAME), 0.0)
    # user_getter returns ({'id': ...}, createdAt)
    user_data, acc_date = user_return
    OWNER_ID = user_data['id']

    # 2) age
    age_str = daily_readme(birthday)

    # 3) LOC (uses caching and may take time)
    total_loc = loc_query(['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'], 7)

    # 4) commits (from cache)
    commit_data = commit_counter(7)

    # 5) stars, repos, contribs
    star_data = graph_repos_stars('stars', ['OWNER'])
    repo_data = graph_repos_stars('repos', ['OWNER'])
    contrib_data = graph_repos_stars('repos', ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'])

    # 6) followers
    follower_data = follower_getter(USER_NAME)

    # format numbers
    try:
        total_loc_formatted = [f"{total_loc[0]:,}", f"{total_loc[1]:,}", f"{total_loc[2]:,}", total_loc[3]]
    except Exception:
        total_loc_formatted = ['0','0','0', True]

    # overwrite svgs
    try:
        svg_overwrite('light_mode.svg', age_str, commit_data, star_data, repo_data, contrib_data, follower_data, total_loc)
        svg_overwrite('dark_mode.svg', age_str, commit_data, star_data, repo_data, contrib_data, follower_data, total_loc)
        print("SVGs updated.")
    except Exception as e:
        print("SVG write failed:", e)

    print("Total GraphQL API calls:", sum(QUERY_COUNT.values()))
