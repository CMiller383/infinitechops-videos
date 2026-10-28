"""Save the Instagram numbers of every posted Reel, so we can see what works.

Run from the root of the public videos repo (post_daily.sh runs it after every posting attempt):
    python3 stats.py            # fetch, write stats.json and add a line to stats_history.jsonl, commit and push
    python3 stats.py --check    # fetch and print only
Needs IG_ACCESS_TOKEN in the environment. Reel insights (views, watch time, shares, saves) need the
instagram_business_manage_insights permission; without it, likes and comments are still saved.
Instagram can take up to 48 h to fill in a new Reel's numbers."""
import calendar, json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

API = os.environ.get('IG_API', 'https://graph.instagram.com/v25.0')
ROOT = os.path.dirname(os.path.abspath(__file__))
METRICS = ['views', 'reach', 'likes', 'comments', 'shares', 'saved', 'total_interactions',
           'ig_reels_avg_watch_time', 'ig_reels_video_view_total_time', 'reels_skip_rate', 'reposts']


class ApiError(Exception):
    pass


def get(path, **params):
    params['access_token'] = os.environ['IG_ACCESS_TOKEN']
    try:
        with urllib.request.urlopen(f'{API}/{path}?' + urllib.parse.urlencode(params), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:            # never print the URL: it holds the token
        body = e.read().decode(errors='replace')
        try:
            err = json.loads(body).get('error', {})
        except ValueError:
            err = {'message': body[:200]}
        if err.get('code') == 190:
            sys.exit('Instagram token is invalid or expired: generate a new one in the Meta app and update IG_ACCESS_TOKEN.')
        raise ApiError(f"{err.get('code')}: {err.get('message', '')[:160]}")
    except urllib.error.URLError as e:
        raise ApiError(f'network: {e.reason}')


def values(data):
    out = {}
    for d in data:
        v = d['values'][0]['value'] if d.get('values') else d.get('total_value', {}).get('value')
        if v is not None:
            out[d['name']] = v
    return out


GOOD = None   # the metrics that worked on the first Reel; later Reels ask for just these in one call


def insights(mid):
    """Every Reel metric this token can read. If the one-shot call fails, ask metric by metric (once per run)."""
    global GOOD
    if GOOD == []:
        return {}, {}
    try:
        return values(get(f'{mid}/insights', metric=','.join(GOOD or METRICS))['data']), {}
    except ApiError:
        if GOOD:
            raise
    out, errs = {}, {}
    for m in METRICS:
        try:
            out.update(values(get(f'{mid}/insights', metric=m)['data']))
        except ApiError as e:
            errs[m] = str(e)
    GOOD = [m for m in METRICS if m not in errs]
    return out, errs


def git(*args):
    return subprocess.run(['git', '-C', ROOT, *args], check=True, capture_output=True, text=True).stdout.strip()


def load(name, default):
    p = os.path.join(ROOT, name)
    return json.load(open(p)) if os.path.exists(p) else default


def main():
    check = '--check' in sys.argv
    now = time.time()
    stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))
    posted = load('posted.json', {})
    me = get('me', fields='user_id,username,followers_count,media_count')
    account = {k: me.get(k) for k in ('username', 'followers_count', 'media_count')}
    print(f"stats {stamp}: @{account['username']}, {account['followers_count']} followers, {account['media_count']} posts")

    old = load('stats.json', {}).get('posts', {})
    posts, errors = {}, {}
    for vid, p in posted.items():
        mid = p['media_id']
        row = {'permalink': p.get('permalink'), 'posted_at': p.get('posted_at')}
        try:
            t0 = calendar.timegm(time.strptime(p['posted_at'], '%Y-%m-%dT%H:%M:%SZ'))
            row['age_hours'] = round((now - t0) / 3600, 1)
        except (KeyError, ValueError):
            pass
        if row.get('age_hours', 0) > 24 * 30 and vid in old:    # past 30 days the numbers barely move: keep the last ones
            posts[vid] = {**old[vid], 'age_hours': row['age_hours']}
            continue
        try:
            info = get(mid, fields='like_count,comments_count')
            row.update(like_count=info.get('like_count'), comments_count=info.get('comments_count'))
            ins, errs = insights(mid)
            row.update(ins)
            if errs:
                errors[vid] = errs
        except ApiError as e:
            errors[vid] = str(e)
        posts[vid] = row
        show = ', '.join(f'{k} {row[k]}' for k in ('views', 'reach', 'ig_reels_avg_watch_time', 'ig_reels_video_view_total_time',
                                                     'reels_skip_rate', 'like_count', 'comments_count', 'shares', 'saved',
                                                     'total_interactions') if row.get(k) is not None)
        print(f"  {vid}: {row.get('age_hours', '?')} h old; {show or 'no numbers yet'}")
    missing = sorted({m for e in errors.values() if isinstance(e, dict) for m in e})
    if missing:
        first = next(iter(next(e for e in errors.values() if isinstance(e, dict)).values()))
        print(f'  could not read: {", ".join(missing)} ({first})')
    for vid, e in errors.items():
        if isinstance(e, str):
            print(f'  {vid}: {e}')
    if check:
        print('check only: nothing saved'); return

    out = {'updated_at': stamp, 'account': account, 'posts': posts}
    if errors:
        out['errors'] = errors
    json.dump(out, open(os.path.join(ROOT, 'stats.json'), 'w'), indent=2)
    keep = ('views', 'reach', 'ig_reels_avg_watch_time', 'like_count', 'comments_count', 'shares', 'saved', 'reels_skip_rate')
    line = {'t': stamp, 'followers': account['followers_count'],
            'posts': {v: {k: r[k] for k in keep if r.get(k) is not None} for v, r in posts.items()}}
    with open(os.path.join(ROOT, 'stats_history.jsonl'), 'a') as f:
        f.write(json.dumps(line, separators=(',', ':')) + '\n')
    git('add', 'stats.json', 'stats_history.jsonl')
    if subprocess.run(['git', '-C', ROOT, 'diff', '--cached', '--quiet']).returncode == 0:
        return
    git('commit', '-m', f'Stats {stamp}')
    try:
        git('push', 'origin', 'HEAD')
    except subprocess.CalledProcessError as e:
        print('warning: stats saved, but could not push:', e.stderr.strip()[:200])


if __name__ == '__main__':
    main()
