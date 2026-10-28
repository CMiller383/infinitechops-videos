# infinitechops videos

Public hosting for @infinitechops Reels. Instagram's API downloads each video from its public link here.

- `queue.json`: videos in posting order, with captions. Add new ones at the end.
- `posted.json`: what has been posted (filled in automatically).
- `post_next.py`: posts the next unposted video through the official Instagram API.
- `post_daily.sh`: daily wrapper (reads the token from `../secrets.txt`, which is never committed).

Schedule: a systemd user timer on the laptop runs it at 7 pm every day.
Check it: `systemctl --user list-timers infinitechops-post.timer`. Pause it: `systemctl --user disable --now infinitechops-post.timer`.
Test without posting: `bash post_daily.sh --check`.
