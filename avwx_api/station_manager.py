"""
Manages station data sourcing
"""

# stdlib
import asyncio as aio
from dataclasses import asdict
from os import environ
from typing import Optional

# library
import httpx

# module
from avwx import Station
from avwx_api_core.token import Token
from avwx_api_core.util.handler import mongo_handler
from avwx_api import app
from avwx_api.structs import ParseConfig


TABLE = "awdata"
AVIOWIKI_URL = "https://api.aviowiki.com/airports/{}"
ENDPOINTS = [
    "",  # airport data
    "/runways/all",  # runways
]
HEADERS = {"Authorization": "Bearer " + environ.get("AVIOWIKI_API_KEY", "")}


async def aid_for_icao(icao: str) -> Optional[str]:
    """Returns the AvioWiki ID for an ICAO ident"""
    if app.mdb is None:
        return
    search = app.mdb.avio.aids.find_one({"_id": icao})
    data = await mongo_handler(search)
    return data["aid"]


async def _call(client: httpx.AsyncClient, endpoint: str, aid: str) -> Optional[dict]:
    url = (AVIOWIKI_URL + endpoint).format(aid)
    try:
        resp = await client.get(url, headers=HEADERS)
    except httpx.RequestError:
        return None
    return resp.json()


async def fetch_from_aviowiki(icao: str) -> Optional[dict]:
    """Fetch airport data from AvioWiki servers"""
    aid = await aid_for_icao(icao)
    async with httpx.AsyncClient(timeout=10) as client:
        coros = [_call(client, e, aid) for e in ENDPOINTS]
        data, runways = await aio.gather(*coros)
    if isinstance(data, dict):
        data["runways"] = runways
    return data


async def get_aviowiki_data(icao: str) -> Optional[dict]:
    """Fetch aviowiki data"""
    if data := await app.cache.get(TABLE, icao):
        del data["_id"]
        return data
    data = await fetch_from_aviowiki(icao)
    await app.cache.update(TABLE, icao, data)
    return data


def _use_aviowiki_data(config: Optional[ParseConfig], token: Optional[Token]) -> bool:
    if app.mdb is None:
        return False
    if config and config.aviowiki_data:
        return True
    if token and ParseConfig.use_aviowiki_data(token):
        return True
    return False


async def station_data_for(
    station: Station,
    config: Optional[ParseConfig] = None,
    token: Optional[Token] = None,
) -> Optional[dict]:
    """Returns airport data dict from station or another source"""
    if _use_aviowiki_data(config, token):
        return await get_aviowiki_data(station.icao)
    return asdict(station)