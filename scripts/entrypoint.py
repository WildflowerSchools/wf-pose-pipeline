from dataclasses import dataclass
from datetime import datetime, timedelta, date, time, timezone
from functools import lru_cache
import logging
import os
from pathlib import Path
from subprocess import run
import time
from zoneinfo import ZoneInfo


import click
from dateutil.parser import parse
import redis


FORMAT = '%(asctime)s %(levelname)s: %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)

ONE_DAY = timedelta(days=1)
TEN_MIN = timedelta(minutes=10)

VIDEO_PATH = os.environ.get("VIDEO_STORAGE_DIR", "/data/dahliasf")
FRAME_PATH = os.environ.get("FRAME_STORAGE_DIR", "/data/dahliasf/frames")

FRAMES_QUEUE_KEY = "frame_dirs"
POSES_QUEUE_KEY = "pose_dirs"
DEAD_FRAMES_QUEUE_KEY = "error_dirs"

@click.group()
def main():
    pass


redclient = redis.Redis(host='localhost', port=6379, db=0)

@main.command()
@click.option('--environment')
@click.option('--tz', default='US/Central')
@click.option('--hours', default='07:30-16:30')
@click.option('--verbose/--quiet', default=False)
@click.option('--reprocess-date', default=None)
@click.option('--check-yesterday', default=True)
@click.option('--include-weekends', default=False)
def queue_jobs(environment, tz, hours, verbose, reprocess_date, check_yesterday, include_weekends):
    # determine date in classroom timezone.
    if verbose:
        logging.info("start-jobs beginning")
        logging.info(f"  current queue length: {redclient.scard(FRAMES_QUEUE_KEY)}")
    tz = ZoneInfo(tz)
    if reprocess_date is None:
        now = datetime.now(timezone.utc)
        classroom_now = now.astimezone(tz)
        start_time, duration = parse_range(hours, classroom_now.date(), tz)
        if verbose:
            logging.info(f"              timezone: {tz} ({tz})")
            logging.info(f"          current time: {now.isoformat()} (UTC)")
            logging.info(f"          current time: {classroom_now.isoformat()} ({tz})")
            logging.info(f"          school hours: {hours}")
            logging.info(f"            start time: {start_time.isoformat()} ({tz})")
            logging.info(f"              duration: {duration}")
    else:
        now = parse(reprocess_date)
        classroom_now = datetime(
            now.year,
            now.month,
            now.day,
            now.hour,
            now.minute,
            now.second,
            tzinfo=tz,
        )
        now = classroom_now.astimezone(timezone.utc)
        check_yesterday = False
        include_weekends = True
        start_time, duration = parse_range(hours, classroom_now.date(), tz)
        if verbose:
            logging.info(f"        timezone: {tz} ({tz})")
            logging.info(f"    process time: {now.isoformat()} (UTC)")
            logging.info(f"    process time: {classroom_now.isoformat()} ({tz})")
            logging.info(f"    school hours: {hours}")
            logging.info(f"      start time: {start_time.isoformat()} ({tz})")
            logging.info(f"        duration: {duration}")
    blocks_to_check = []
    # does the date fall under a weekday
    day_of_week = classroom_now.isoweekday()
    if check_yesterday and (1 < day_of_week < 7 or include_weekends):
        cdate = start_time - ONE_DAY
        end = cdate + duration
        while cdate < end:
            blocks_to_check.append(cdate)
            cdate += TEN_MIN
        if verbose:
            logging.info("       yesterday: ok")
    if day_of_week < 6 or include_weekends:
        cdate = start_time
        end = start_time + duration
        while cdate < end:
            blocks_to_check.append(cdate)
            cdate += TEN_MIN
        if verbose:
            logging.info("           today: ok")
    if verbose:
        logging.info(f" blocks to check: {len(blocks_to_check)}")
    queue = []
    for b in blocks_to_check:
        qe2 = check_block(environment, b, verbose)
        queue = queue + qe2
    logging.info(f"blocks that need to be addreessed: {len(queue)}")


def check_block(environment, start_time, verbose):
    camera_paths = get_camera_paths(environment)
    date_portion = start_time.strftime("%Y/%m/%d/%H/")
    min_digit_prefix = start_time.strftime("%M")[0:1]
    queue = []
    for camera_path in camera_paths:
        hour_directory = camera_path / date_portion
        file_count = 0
        if hour_directory.exists():
            for video in hour_directory.iterdir():
                if video.is_file() and video.name.startswith(min_digit_prefix):
                    file_count += 1
        if file_count > 58:  # 2 missing videos is an acceptable tolerance
            # an adaquate number of videos exist.
            # check to see if frames have already been extracted
            rel_path = hour_directory.relative_to(VIDEO_PATH)
            block_frames_path = FRAME_PATH / rel_path / f"frames__{min_digit_prefix}"
            file_count = 0
            if block_frames_path.exists():
                if (block_frames_path / "alphapose-result.json").exists():
                    file_count = 99999 # put it above the threshold to skip
                for image in hour_directory.iterdir():
                    if image.is_file():
                        file_count += 1
            if file_count < 5800:
                queue.append(block_frames_path)
                redclient.sadd(FRAMES_QUEUE_KEY, "|".join([str(block_frames_path), str(hour_directory), str(min_digit_prefix)]))
                if verbose:
                    logging.info(f"frames {block_frames_path}: {file_count}")
            elif file_count < 99999:
                queue.append(block_frames_path)
                redclient.sadd(POSES_QUEUE_KEY, "|".join([str(block_frames_path), str(hour_directory), str(min_digit_prefix)]))
                if verbose:
                    logging.info(f"poses  {block_frames_path}: {file_count}")

    return queue


@lru_cache
def get_camera_paths(environment):
    classroom_root_path = Path(f"{VIDEO_PATH}/{environment}")
    camera_paths = list()
    for camera in classroom_root_path.iterdir():
        if len(camera.name) == 36:
            camera_paths.append(camera)
    return camera_paths

def parse_range(hours, dte, tz):
    s, e = hours.split("-")
    start = construct_datetime(dte, parse(s), tz)
    end = construct_datetime(dte, parse(e), tz)
    duration = end - start
    return start, duration


def construct_datetime(dte, time, tz):
    return datetime(
        dte.year,
        dte.month,
        dte.day,
        time.hour,
        time.minute,
        time.second,
        tzinfo=tz,
    )


@main.command()
@click.option('--verbose/--quiet', default=False)
def frames_worker(verbose):
    if verbose:
        logging.info("frames-worker starting")
        logging.info(f"  current queue length: {redclient.scard(FRAMES_QUEUE_KEY)}")
    while True:
        next_path = redclient.spop(FRAMES_QUEUE_KEY)
        if next_path is None:
            if verbose:
                logging.info(f"queue is empty")
            time.sleep(10)
        else:
            frames_dir, hour_dir, prefix = next_path.decode("utf8").split("|")
            frames_dir = Path(frames_dir)
            hour_dir = Path(hour_dir)
            frames_dir.mkdir(parents=True, exist_ok=True)
            if verbose:
                logging.info(f"starting on {frames_dir.relative_to(frames_dir.parent.parent.parent.parent.parent.parent.parent)}")
            for video in hour_dir.iterdir():
                if video.name.startswith(prefix):
                    logging.info(f"processing video {str(video)}")
                    cp = run(
                        [
                            "ffmpeg",
                            "-i",
                            str(video),
                            f"{str(frames_dir)}/{(video.name)[0:5]}_%03d.png"
                        ],
                        check=True,
                        capture_output=True,
                    )
                    if cp.returncode != 0:
                        logging.info(f"processing video {str(video)} failed")
                        redclient.sadd(DEAD_FRAMES_QUEUE_KEY, next_path)
            return




if __name__ == '__main__':
    main()

