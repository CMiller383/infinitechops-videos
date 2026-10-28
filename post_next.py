"""Post the next queued video to Instagram as a Reel, through the official Instagram API (Instagram Login).

Run from the root of the public videos repo:
    python3 post_next.py            # publish the next unposted item in queue.json
    python3 post_next.py --check    # verify token, account and the next video's public link; publish nothing
Needs IG_ACCESS_TOKEN in the environment. Instagram downloads the video itself from the repo's raw GitHub link,
so the file must already be pushed. After a successful post it records the result in posted.json and pushes."""
import json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

API = 'https://graph.instagram.com/v25.0'
ROOT = os.path.dirname(os.path.abspath(__file__))


def call(method, path, **params):
    params['access_token'] = os.environ['IG_ACCESS_TOKEN']
    url = f'{API}/{path}'
    data = None
    if method == 'GET':
        url += '?' + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        try:
            err = json.loads(body).get('error', {})
        except ValueError:
            err = {'message': body[:300]}
        if err.get('code') == 190:
            sys.exit('Instagram token is invalid or expired: generate a new one in the Meta app and update IG_ACCESS_TOKEN.')
        sys.exit(f'Instagram API error on {method} {path}: {err}')


def git(*args):
    return subprocess.run(['git', '-C', ROOT, *args], check=True, capture_output=True, text=True).stdout.strip()


def raw_base():
    url = git('remote', 'get-url', 'origin')
    slug = url.split('github.com')[-1].lstrip(':/').removesuffix('.git')
    if '/git/' in url and 'github.com' not in url:          # proxied remotes look like http://host/git/owner/repo
        slug = url.split('/git/')[-1].removesuffix('.git')
    return f'https://raw.githubusercontent.com/{slug}/{git("rev-parse", "--abbrev-ref", "HEAD")}'


def load(name, default):
    p = os.path.join(ROOT, name)
    return json.load(open(p)) if os.path.exists(p) else default


def main():
    check = '--check' in sys.argv
    queue = load('queue.json', {'posts': []})['posts']
    posted = load('posted.json', {})
    nxt = next((q for q in queue if q['id'] not in posted), None)

    me = call('GET', 'me', fields='user_id,username')
    ig_id = me.get('user_id') or me['id']
    print(f"account: @{me.get('username')} ({ig_id})")
    limit = call('GET', f'{ig_id}/content_publishing_limit', fields='quota_usage')
    print('posts used in the last 24 h:', limit.get('data', [{}])[0].get('quota_usage'))
    if not nxt:
        print('queue is empty: nothing to post'); sys.exit(3)

    video_url = f"{raw_base()}/{nxt['file']}"
    try:
        with urllib.request.urlopen(urllib.request.Request(video_url, method='HEAD'), timeout=30) as r:
            print('video link ok:', video_url, r.headers.get('Content-Length'), 'bytes')
    except urllib.error.URLError as e:
        sys.exit(f'video link not reachable ({e}); is the file pushed? {video_url}')
    if check:
        print('check only: next up is', nxt['id']); return

    c = call('POST', f'{ig_id}/media', media_type='REELS', video_url=video_url, caption=nxt['caption'], share_to_feed='true')
    cid = c['id']; print('container', cid)
    for _ in range(40):                                    # Instagram processes the video; allow up to ~10 minutes
        time.sleep(15)
        st = call('GET', cid, fields='status_code,status').get('status_code')
        print('status', st)
        if st == 'FINISHED': break
        if st in ('ERROR', 'EXPIRED'): sys.exit(f'Instagram could not process the video: {st}')
    else:
        sys.exit('Instagram took too long to process the video; try again later (the container expires in 24 h).')
    pub = call('POST', f'{ig_id}/media_publish', creation_id=cid)
    link = call('GET', pub['id'], fields='permalink').get('permalink')
    print('published', pub['id'], link)

    posted[nxt['id']] = {'media_id': pub['id'], 'permalink': link, 'posted_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    json.dump(posted, open(os.path.join(ROOT, 'posted.json'), 'w'), indent=2)
    git('add', 'posted.json'); git('commit', '-m', f"Posted {nxt['id']}")
    try:
        git('push', 'origin', 'HEAD')
    except subprocess.CalledProcessError as e:
        print('warning: posted, but could not push posted.json:', e.stderr)


if __name__ == '__main__':
    main()
