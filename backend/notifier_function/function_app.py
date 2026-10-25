"""
Three timers:

  - live_notifier: goal and final-score push notifications, every minute
    (UTC hours 16-23 and 0-7, noon-4am ET).
  - closing_odds: every 5 minutes while games can start (UTC 15-23 and
    0-4); snapshots the market near puck drop (market_odds.log_closing).
  - post_reminder: every 10 minutes, UTC 14-17 (the morning ET); once a
    day after a game night, tells the creator's devices that Swing of the
    Night is ready to post (notify_live_games.creator_reminder).

It used to be the nhl-live-notifier Container Apps Job, which started a
fresh container 960 times a day (about 25 s each, almost all startup) and
alone used more than the monthly free Container Apps compute. A Flex
Consumption function keeps a warm worker between runs and bills only the
second or two each run takes, well inside its free grant.

The deploy copies the backend modules these use in next to this file
(scripts/package_notifier.py).
"""

import logging

import azure.functions as func

import market_odds
import notify_live_games

app = func.FunctionApp()

# The Functions worker forwards log records that reach the root logger to
# the host (and App Insights). setup_logging gives each module its own
# console handler and turns propagation off, which would hide every line.
for module in (notify_live_games, market_odds):
    module.logger.handlers.clear()
    module.logger.propagate = True


# NCRONTAB has a seconds field; the Functions host runs in UTC.
@app.timer_trigger(arg_name="timer", schedule="0 * 0-7,16-23 * * *", run_on_startup=False, use_monitor=False)
def live_notifier(timer: func.TimerRequest) -> None:
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    notify_live_games.logger.info("Sent %d notifications", notify_live_games.run())


@app.timer_trigger(arg_name="timer", schedule="30 */5 0-4,15-23 * * *", run_on_startup=False, use_monitor=False)
def closing_odds(timer: func.TimerRequest) -> None:
    market_odds.log_closing()


@app.timer_trigger(arg_name="timer", schedule="15 */10 14-17 * * *", run_on_startup=False, use_monitor=False)
def post_reminder(timer: func.TimerRequest) -> None:
    notify_live_games.creator_reminder()
