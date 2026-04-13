# Scheduling

## Option A: Linux/macOS cron

Run at 08:00 every day:

0 8 * * * cd /path/to/danxi-daily && /usr/bin/python3 scripts/generate_daily.py --hours 24 --top 12 >> outputs/cron.log 2>&1

## Option B: Windows Task Scheduler

Create a daily task at 08:00:

Program/script:
python

Arguments:
scripts/generate_daily.py --hours 24 --top 12

Start in:
C:\path\to\danxi-daily

## Option C: Agent-based CronCreate prompt

Use this prompt inside your coding agent:

Create a daily scheduled task at 08:00 local time to run:
python scripts/generate_daily.py --hours 24 --top 12
in the danxi-daily project root, and write logs to outputs/cron.log.

## Recommended Safety

- Keep posting disabled in scheduled runs unless fully verified.
- Monitor outputs/cron.log and outputs/daily.md each morning.
