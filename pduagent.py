# Copyright 2021 Foundries.io
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import aiohttp
import argparse
import asyncio
import contextlib
import json
import logging
import sys
import shlex
import subprocess
import time
import yaml

from dotmap import DotMap


async def listen_for_events(config, event: asyncio.Event) -> None:
    LOG = logging.getLogger("pduagent")
    LOG.info("Starting event listener")
    headers = {
        "Authorization": f"Token: {config.token}"
    }
    while True:
        with contextlib.suppress(aiohttp.ClientError):
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.ws_connect(config.url) as ws:
                    LOG.info("Session connected")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.CLOSE:
                            LOG.info("server closing")
                            sys.exit(0)
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            data = json.loads(msg.data)
                            LOG.info(data)
                            # execute command
                            # this looks extremely insecure
                            if "error" in data.keys():
                                LOG.error("Received error: %s" % data["error"])
                                await ws.close()
                                sys.exit(1)
                            if "cmd" in data.keys():
                                LOG.info("Executing cmd: %s" % data["cmd"])
                                args = shlex.split(data["cmd"])
                                LOG.debug(args)
                                subprocess.run(args, check=True, shell=True)
                        except ValueError:
                            LOG.error("[EVENT] Invalid message: %s", msg)
                            continue
                        except subprocess.SubprocessError:
                            LOG.error("Subprocess exited")
                            continue
        await asyncio.sleep(1)

async def main(config):
    event = asyncio.Event()
    await asyncio.gather(
        listen_for_events(config, event)
    )


parser = argparse.ArgumentParser()

parser.add_argument(
    "--config",
    required=True,
    help="Path of the Agent config file"
)
parser.add_argument(
    "--logfile",
    help="Path to the file that contains logs"
)
parser.add_argument(
    "--loglevel",
    default="INFO",
    help="Path to the file that contains logs"
)

args = parser.parse_args()

config = None
with open(args.config, "r") as conf_file:
    try:
        yaml_config = yaml.safe_load(conf_file)
        config = DotMap(yaml_config)
    except yaml.YAMLError as exc:
        sys.exit(1)

loglevel = logging.getLevelName(args.loglevel)

logging.Formatter.convert = time.gmtime
FORMAT = "%(asctime)-15s %(levelname)7s %(message)s"
formatter = logging.Formatter(FORMAT)
LOG = logging.getLogger("pduagent")
LOG.setLevel(loglevel)
if not args.logfile:
    handler = logging.StreamHandler()
else:
    handler = logging.FileHandler(args.logfile)
handler.setLevel(loglevel)
handler.setFormatter(formatter)
LOG.addHandler(handler)

if not config:
    LOG.error("Config is empty")
    sys.exit(1)

if not config.url or not config.token:
    LOG.error("Config doesn't include url or token")
    sys.exit(1)
try:
    sys.exit(asyncio.run(main(config)))
except KeyboardInterrupt:
    LOG.warning("[EXIT] Received Ctrl+C")
    sys.exit(1)
