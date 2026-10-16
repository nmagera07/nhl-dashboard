"""
Goal and final-score push notifications as an Azure Functions timer, every
minute during game hours (UTC hours 16-23 and 0-7, noon-4am ET).

It used to be the nhl-live-notifier Container Apps Job, which started a
fresh container 960 times a day (about 25 s each, almost all startup) and
alone used more than the monthly free Container Apps compute. A Flex
Consumption function keeps a warm worker between runs and bills only the
second or two each run takes, well inside its free grant.

The deploy copies notify_live_games.py, push.py, and logging_config.py in
next to this file (see .github/workflows/backend-deploy.yml).
"""

import logging

import azure.functions as func

import notify_live_games

app = func.FunctionApp()

# The Functions worker already forwards log records to the host; the
# notifier's own console handler would print each line a second time.
notify_live_games.logger.handlers.clear()


# NCRONTAB has a seconds field; the Functions host runs in UTC.
@app.timer_trigger(arg_name="timer", schedule="0 * 0-7,16-23 * * *", run_on_startup=False, use_monitor=False)
def live_notifier(timer: func.TimerRequest) -> None:
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    notify_live_games.logger.info("Sent %d notifications", notify_live_games.run())
