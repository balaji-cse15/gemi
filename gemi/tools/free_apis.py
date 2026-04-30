"""Free-API tools — curated set of public APIs that need no key (or have a
generous unauthenticated tier).

All tools are SAFE-tier (read-only) and use httpx with reasonable timeouts.

Tools:
  hn_top, hn_item        Hacker News
  weather                Open-Meteo (current + forecast, no key)
  currency               Frankfurter ECB exchange rates
  wiki                   Wikipedia article summary
  arxiv_search           Arxiv academic papers
  reddit                 Reddit public JSON endpoint
  nasa_apod              NASA Astronomy Picture of the Day
  country                REST Countries
  ip_lookup              IP geolocation (ip-api.com)
  crypto_price           Coingecko-free crypto prices
  pokemon                PokeAPI
  stackexchange          Stack Exchange question search
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx

from .base import Tool, ToolResult


_UA = (
    "Mozilla/5.0 (Buddy CLI; +https://github.com/) "
    "Python/httpx free-api tools"
)


def _http_get(url: str, params: dict | None = None, headers: dict | None = None,
              timeout: int = 15) -> tuple[Any, str]:
    """GET helper. Returns (parsed_or_text, error_message)."""
    h = {"User-Agent": _UA, "Accept": "application/json"}
    if headers:
        h.update(headers)
    try:
        resp = httpx.get(url, params=params, headers=h, timeout=timeout, follow_redirects=True)
    except httpx.TimeoutException:
        return None, "request timed out"
    except Exception as e:
        return None, f"request failed: {e}"
    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
    ct = resp.headers.get("content-type", "")
    if "json" in ct:
        try:
            return resp.json(), ""
        except Exception:
            return resp.text, ""
    return resp.text, ""


# =================================================================
# Hacker News
# =================================================================

class HnTopTool(Tool):
    name = "hn_top"
    read_only = True
    description = (
        "Get top stories from Hacker News. Returns title, points, comments, URL. "
        "Free, no API key."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Max stories (default 10, max 30).", "default": 10},
            "kind": {"type": "string", "description": "topstories|newstories|beststories|askstories|showstories",
                     "default": "topstories"},
        },
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        limit = min(int(kwargs.get("limit", 10)), 30)
        kind = kwargs.get("kind", "topstories")
        if kind not in {"topstories", "newstories", "beststories", "askstories", "showstories"}:
            return ToolResult.fail(f"invalid kind: {kind}")

        ids, err = _http_get(f"https://hacker-news.firebaseio.com/v0/{kind}.json")
        if err:
            return ToolResult.fail(err)
        if not isinstance(ids, list):
            return ToolResult.fail("unexpected HN response")

        lines = [f"# Hacker News — {kind} (top {limit})\n"]
        for i, hn_id in enumerate(ids[:limit], 1):
            item, _ = _http_get(f"https://hacker-news.firebaseio.com/v0/item/{hn_id}.json")
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            score = item.get("score", 0)
            comments = item.get("descendants", 0)
            url = item.get("url") or f"https://news.ycombinator.com/item?id={hn_id}"
            by = item.get("by", "?")
            lines.append(f"{i:2}. [{score:>4}↑ {comments:>3}c] {title}")
            lines.append(f"      by {by} — {url}")
        return ToolResult.ok("\n".join(lines))


class HnItemTool(Tool):
    name = "hn_item"
    read_only = True
    description = "Get a single Hacker News item by id (story, comment, poll)."
    input_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer", "description": "HN item id"}},
        "required": ["id"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        try:
            item_id = int(kwargs.get("id", 0))
        except (TypeError, ValueError):
            return ToolResult.fail("invalid id")
        item, err = _http_get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
        if err:
            return ToolResult.fail(err)
        if not isinstance(item, dict):
            return ToolResult.fail("item not found")
        return ToolResult.ok(json.dumps(item, indent=2)[:5000])


# =================================================================
# Weather (Open-Meteo)
# =================================================================

class WeatherTool(Tool):
    name = "weather"
    read_only = True
    description = (
        "Current weather + 3-day forecast via Open-Meteo. Pass either "
        "'lat'+'lon' OR 'place' (free-text geocode lookup). No API key."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "place": {"type": "string", "description": "Place name (e.g. 'Paris', 'San Francisco')."},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "units": {"type": "string", "description": "metric|imperial (default metric)", "default": "metric"},
        },
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        place = kwargs.get("place", "")
        lat = kwargs.get("lat")
        lon = kwargs.get("lon")
        units = kwargs.get("units", "metric")

        if not (lat is not None and lon is not None) and place:
            geo, err = _http_get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": place, "count": 1, "language": "en"},
            )
            if err:
                return ToolResult.fail(f"geocode: {err}")
            results = (geo or {}).get("results") or []
            if not results:
                return ToolResult.fail(f"no geocode match for '{place}'")
            r = results[0]
            lat = r["latitude"]
            lon = r["longitude"]
            place_label = f"{r.get('name', place)}, {r.get('country', '')}"
        else:
            place_label = f"{lat},{lon}"

        if lat is None or lon is None:
            return ToolResult.fail("provide lat+lon or place")

        temp_unit = "celsius" if units == "metric" else "fahrenheit"
        wind_unit = "kmh" if units == "metric" else "mph"
        data, err = _http_get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum",
                "temperature_unit": temp_unit, "wind_speed_unit": wind_unit,
                "timezone": "auto", "forecast_days": 3,
            },
        )
        if err:
            return ToolResult.fail(err)

        cur = (data or {}).get("current", {})
        daily = (data or {}).get("daily", {})
        unit_t = "°C" if units == "metric" else "°F"
        unit_w = "km/h" if units == "metric" else "mph"

        lines = [f"# Weather — {place_label}", ""]
        if cur:
            lines.append(f"Current: {cur.get('temperature_2m', '?')}{unit_t}  "
                         f"humidity {cur.get('relative_humidity_2m', '?')}%  "
                         f"wind {cur.get('wind_speed_10m', '?')} {unit_w}  "
                         f"code {cur.get('weather_code', '?')}")
        if daily.get("time"):
            lines.append("\nForecast:")
            for i, day in enumerate(daily["time"]):
                lo = daily["temperature_2m_min"][i]
                hi = daily["temperature_2m_max"][i]
                pcp = daily["precipitation_sum"][i]
                lines.append(f"  {day}  lo {lo}{unit_t} / hi {hi}{unit_t}  rain {pcp}mm")
        return ToolResult.ok("\n".join(lines))


# =================================================================
# Currency (Frankfurter / ECB)
# =================================================================

class CurrencyTool(Tool):
    name = "currency"
    read_only = True
    description = (
        "FX rates and currency conversion via Frankfurter (ECB data, no key). "
        "Use 'amount' + 'from' + 'to' for conversion, or just 'from' to list rates."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "amount": {"type": "number", "default": 1},
            "from": {"type": "string", "description": "ISO 4217 code (e.g. USD, EUR)"},
            "to": {"type": "string", "description": "Target ISO 4217 (or omit for all)"},
            "date": {"type": "string", "description": "YYYY-MM-DD for historical (default today)"},
        },
        "required": ["from"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        from_ccy = (kwargs.get("from") or "").upper()
        to_ccy = (kwargs.get("to") or "").upper()
        amount = float(kwargs.get("amount", 1))
        date = kwargs.get("date", "latest")
        if not from_ccy:
            return ToolResult.fail("missing 'from' currency")

        url = f"https://api.frankfurter.app/{date}"
        params = {"from": from_ccy, "amount": amount}
        if to_ccy:
            params["to"] = to_ccy
        data, err = _http_get(url, params=params)
        if err:
            return ToolResult.fail(err)
        if not isinstance(data, dict):
            return ToolResult.fail("unexpected response")

        out = [f"# {amount} {from_ccy} → on {data.get('date', '?')}"]
        rates = data.get("rates", {})
        for ccy, val in sorted(rates.items()):
            out.append(f"  {ccy}: {val:,.4f}")
        return ToolResult.ok("\n".join(out))


# =================================================================
# Wikipedia
# =================================================================

class WikiTool(Tool):
    name = "wiki"
    read_only = True
    description = "Search Wikipedia and return a summary. No key."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "lang": {"type": "string", "default": "en"},
            "full": {"type": "boolean", "description": "Return full extract instead of summary",
                     "default": False},
        },
        "required": ["query"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        q = (kwargs.get("query") or "").strip()
        lang = kwargs.get("lang", "en")
        full = bool(kwargs.get("full", False))
        if not q:
            return ToolResult.fail("empty query")

        # Use REST API summary endpoint (clean, fast)
        endpoint = "https://" + lang + ".wikipedia.org/api/rest_v1/page/summary/" + quote_plus(q.replace(" ", "_"))
        data, err = _http_get(endpoint)
        if err:
            # Fall back to OpenSearch then summary
            sr, _ = _http_get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action": "opensearch", "search": q, "limit": 1, "format": "json"},
            )
            if isinstance(sr, list) and len(sr) > 1 and sr[1]:
                title = sr[1][0]
                endpoint = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote_plus(title)}"
                data, err = _http_get(endpoint)
            if err:
                return ToolResult.fail(err)
        if not isinstance(data, dict):
            return ToolResult.fail("unexpected response")

        title = data.get("title", q)
        url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        summary = data.get("extract", "(no summary)")
        if full:
            # fetch full extract separately
            full_data, _ = _http_get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action": "query", "prop": "extracts", "explaintext": 1,
                        "titles": title, "format": "json"},
            )
            try:
                pages = list((full_data or {}).get("query", {}).get("pages", {}).values())
                if pages:
                    summary = pages[0].get("extract", summary)
            except Exception:
                pass
        return ToolResult.ok(f"# {title}\n{url}\n\n{summary}")


# =================================================================
# Arxiv
# =================================================================

class ArxivTool(Tool):
    name = "arxiv_search"
    read_only = True
    description = "Search Arxiv for academic papers. Returns title, authors, abstract, link."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
            "sort_by": {"type": "string", "default": "relevance",
                        "description": "relevance|lastUpdatedDate|submittedDate"},
        },
        "required": ["query"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        q = (kwargs.get("query") or "").strip()
        if not q:
            return ToolResult.fail("empty query")
        max_results = min(int(kwargs.get("max_results", 5)), 20)
        sort_by = kwargs.get("sort_by", "relevance")

        url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{q}",
            "max_results": max_results,
            "sortBy": sort_by,
        }
        text, err = _http_get(url, params=params)
        if err:
            return ToolResult.fail(err)
        if not isinstance(text, str):
            return ToolResult.fail("unexpected response")

        # Parse Atom XML by regex (avoid heavy XML deps)
        entry_re = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)
        title_re = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL)
        author_re = re.compile(r"<author>\s*<name>(.*?)</name>", re.DOTALL)
        summary_re = re.compile(r"<summary[^>]*>(.*?)</summary>", re.DOTALL)
        link_re = re.compile(r'<link[^>]+rel="alternate"[^>]+href="([^"]+)"')

        out = [f"# Arxiv: {q}  ({max_results} results)\n"]
        for entry in entry_re.findall(text):
            title = (title_re.search(entry) or [None]).group(1).strip().replace("\n", " ") if title_re.search(entry) else "?"
            authors = ", ".join(author_re.findall(entry)[:5])
            link = (link_re.search(entry) or [None]).group(1) if link_re.search(entry) else "?"
            summary = (summary_re.search(entry) or [None]).group(1).strip()[:400] if summary_re.search(entry) else ""
            out.append(f"## {title}")
            out.append(f"   {authors}")
            out.append(f"   {link}")
            out.append(f"   {summary}…")
            out.append("")
        return ToolResult.ok("\n".join(out))


# =================================================================
# Reddit (public JSON, no auth)
# =================================================================

class RedditTool(Tool):
    name = "reddit"
    read_only = True
    description = (
        "Read a Reddit subreddit's top/hot/new posts via the public .json endpoint. "
        "No auth. Use 'subreddit' + 'kind' (hot/new/top/rising)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "subreddit": {"type": "string"},
            "kind": {"type": "string", "default": "hot"},
            "limit": {"type": "integer", "default": 10},
            "time": {"type": "string", "default": "day", "description": "hour|day|week|month|year|all"},
        },
        "required": ["subreddit"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        sub = (kwargs.get("subreddit") or "").lstrip("/r/").strip("/")
        if not sub:
            return ToolResult.fail("empty subreddit")
        kind = kwargs.get("kind", "hot")
        if kind not in {"hot", "new", "top", "rising", "controversial"}:
            return ToolResult.fail(f"invalid kind: {kind}")
        limit = min(int(kwargs.get("limit", 10)), 30)
        time_filter = kwargs.get("time", "day")

        url = f"https://www.reddit.com/r/{sub}/{kind}.json"
        params = {"limit": limit}
        if kind in ("top", "controversial"):
            params["t"] = time_filter
        data, err = _http_get(url, params=params, headers={"User-Agent": _UA})
        if err:
            return ToolResult.fail(err)
        children = (data or {}).get("data", {}).get("children", [])
        if not children:
            return ToolResult.fail("no posts")

        out = [f"# r/{sub} — {kind}", ""]
        for i, c in enumerate(children[:limit], 1):
            d = c.get("data", {})
            title = d.get("title", "?")[:120]
            score = d.get("score", 0)
            comments = d.get("num_comments", 0)
            url = "https://reddit.com" + d.get("permalink", "")
            flair = d.get("link_flair_text") or ""
            flair_str = f" [{flair}]" if flair else ""
            out.append(f"{i:2}. [{score:>5}↑ {comments:>3}c]{flair_str} {title}")
            out.append(f"      {url}")
        return ToolResult.ok("\n".join(out))


# =================================================================
# NASA Astronomy Picture of the Day
# =================================================================

class NasaApodTool(Tool):
    name = "nasa_apod"
    read_only = True
    description = (
        "NASA Astronomy Picture of the Day. Uses DEMO_KEY (limited) by default. "
        "Pass api_key for higher rate limit (free at api.nasa.gov)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "YYYY-MM-DD (default today)"},
            "api_key": {"type": "string", "description": "Optional NASA api key"},
        },
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        params = {"api_key": kwargs.get("api_key") or "DEMO_KEY"}
        if kwargs.get("date"):
            params["date"] = kwargs["date"]
        data, err = _http_get("https://api.nasa.gov/planetary/apod", params=params)
        if err:
            return ToolResult.fail(err)
        if not isinstance(data, dict):
            return ToolResult.fail("unexpected response")
        return ToolResult.ok(
            f"# {data.get('title', '?')}  ({data.get('date', '?')})\n"
            f"{data.get('url', '')}\n"
            f"HD: {data.get('hdurl', '')}\n\n"
            f"{data.get('explanation', '')[:2000]}"
        )


# =================================================================
# REST Countries
# =================================================================

class CountryTool(Tool):
    name = "country"
    read_only = True
    description = "Look up a country: capital, population, languages, area, currencies, flag."
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Country name (full or partial)"},
            "code": {"type": "string", "description": "ISO 3166-1 alpha-2/-3 code"},
        },
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        name = (kwargs.get("name") or "").strip()
        code = (kwargs.get("code") or "").strip()
        if code:
            url = f"https://restcountries.com/v3.1/alpha/{quote_plus(code)}"
        elif name:
            url = f"https://restcountries.com/v3.1/name/{quote_plus(name)}"
        else:
            return ToolResult.fail("provide name or code")
        data, err = _http_get(url)
        if err:
            return ToolResult.fail(err)
        if not isinstance(data, list) or not data:
            return ToolResult.fail("not found")
        c = data[0]
        names = c.get("name", {})
        capital = ", ".join(c.get("capital", []) or [])
        langs = ", ".join((c.get("languages") or {}).values())
        currencies = ", ".join(
            f"{cd.get('name', k)} ({cd.get('symbol', '')})"
            for k, cd in (c.get("currencies") or {}).items()
        )
        return ToolResult.ok(
            f"# {names.get('official', '?')}  ({c.get('cca2', '?')} / {c.get('cca3', '?')})\n"
            f"capital:    {capital}\n"
            f"region:     {c.get('region', '?')} / {c.get('subregion', '?')}\n"
            f"population: {c.get('population', 0):,}\n"
            f"area:       {c.get('area', 0):,} km²\n"
            f"languages:  {langs}\n"
            f"currencies: {currencies}\n"
            f"timezones:  {', '.join((c.get('timezones') or [])[:5])}\n"
            f"flag:       {c.get('flag', '')}  {c.get('flags', {}).get('png', '')}"
        )


# =================================================================
# IP Geolocation (ip-api.com — free for non-commercial, no key)
# =================================================================

class IpLookupTool(Tool):
    name = "ip_lookup"
    read_only = True
    description = (
        "Look up an IP address: country, city, ISP, lat/lon. Uses ip-api.com "
        "(free for non-commercial; rate-limited to 45/min)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "ip": {"type": "string", "description": "IP address. Leave empty for own IP."},
        },
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        ip = (kwargs.get("ip") or "").strip()
        url = f"http://ip-api.com/json/{quote_plus(ip)}" if ip else "http://ip-api.com/json/"
        data, err = _http_get(url)
        if err:
            return ToolResult.fail(err)
        if not isinstance(data, dict):
            return ToolResult.fail("unexpected response")
        if data.get("status") != "success":
            return ToolResult.fail(data.get("message", "lookup failed"))
        return ToolResult.ok(
            f"# IP: {data.get('query', '?')}\n"
            f"country: {data.get('country', '?')} ({data.get('countryCode', '')})\n"
            f"region:  {data.get('regionName', '')}, {data.get('city', '')}\n"
            f"zip:     {data.get('zip', '')}\n"
            f"latlon:  {data.get('lat', 0)}, {data.get('lon', 0)}\n"
            f"isp:     {data.get('isp', '')}\n"
            f"org:     {data.get('org', '')}\n"
            f"as:      {data.get('as', '')}\n"
            f"tz:      {data.get('timezone', '')}"
        )


# =================================================================
# Crypto prices (Coingecko free)
# =================================================================

class CryptoPriceTool(Tool):
    name = "crypto_price"
    read_only = True
    description = (
        "Crypto spot prices via CoinGecko (free, no key). Pass a comma-separated "
        "list of coin IDs (bitcoin, ethereum, solana, etc.)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "ids": {"type": "string", "description": "Comma-separated CoinGecko ids", "default": "bitcoin,ethereum,solana"},
            "vs": {"type": "string", "description": "Comma-separated fiat ids", "default": "usd"},
        },
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        ids = kwargs.get("ids") or "bitcoin,ethereum,solana"
        vs = kwargs.get("vs") or "usd"
        data, err = _http_get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": vs,
                    "include_24hr_change": "true", "include_market_cap": "true"},
        )
        if err:
            return ToolResult.fail(err)
        if not isinstance(data, dict) or not data:
            return ToolResult.fail("no data (rate limited?)")
        lines = ["# Crypto prices"]
        for coin_id in [c.strip() for c in ids.split(",")]:
            if coin_id not in data:
                continue
            entry = data[coin_id]
            for vs_ccy in [v.strip() for v in vs.split(",")]:
                price = entry.get(vs_ccy)
                change = entry.get(f"{vs_ccy}_24h_change", 0)
                mcap = entry.get(f"{vs_ccy}_market_cap", 0)
                if price is None:
                    continue
                arrow = "▲" if change >= 0 else "▼"
                lines.append(
                    f"  {coin_id:<14} {vs_ccy.upper():<4}  "
                    f"${price:>14,.2f}  {arrow}{abs(change):.2f}%  "
                    f"mcap ${mcap/1e9:.1f}B"
                )
        return ToolResult.ok("\n".join(lines))


# =================================================================
# Pokemon (PokeAPI)
# =================================================================

class PokemonTool(Tool):
    name = "pokemon"
    read_only = True
    description = "Look up a Pokemon by name or id. Returns types, stats, abilities, height, weight."
    input_schema = {
        "type": "object",
        "properties": {
            "name_or_id": {"type": "string"},
        },
        "required": ["name_or_id"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        name = (kwargs.get("name_or_id") or "").lower().strip()
        if not name:
            return ToolResult.fail("empty name")
        data, err = _http_get(f"https://pokeapi.co/api/v2/pokemon/{quote_plus(name)}")
        if err:
            return ToolResult.fail(err)
        if not isinstance(data, dict):
            return ToolResult.fail("not found")
        types = ", ".join(t["type"]["name"] for t in data.get("types", []))
        abilities = ", ".join(a["ability"]["name"] for a in data.get("abilities", []))
        stats = " · ".join(
            f"{s['stat']['name']}={s['base_stat']}" for s in data.get("stats", [])
        )
        return ToolResult.ok(
            f"# {data.get('name', '?').title()}  #{data.get('id', '?')}\n"
            f"types:     {types}\n"
            f"abilities: {abilities}\n"
            f"height:    {data.get('height', 0)/10}m\n"
            f"weight:    {data.get('weight', 0)/10}kg\n"
            f"stats:     {stats}\n"
            f"sprite:    {data.get('sprites', {}).get('front_default', '')}"
        )


# =================================================================
# StackExchange (StackOverflow + others)
# =================================================================

class StackExchangeTool(Tool):
    name = "stackexchange"
    read_only = True
    description = (
        "Search StackExchange (StackOverflow by default). Free, no key for "
        "small volume. Returns top question titles + scores + answer count."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "site": {"type": "string", "default": "stackoverflow",
                     "description": "stackoverflow|serverfault|superuser|askubuntu|..."},
            "tagged": {"type": "string", "description": "Optional tag filter"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        q = (kwargs.get("query") or "").strip()
        if not q:
            return ToolResult.fail("empty query")
        site = kwargs.get("site", "stackoverflow")
        tagged = kwargs.get("tagged", "")
        limit = min(int(kwargs.get("limit", 10)), 25)

        params = {
            "order": "desc", "sort": "relevance",
            "q": q, "site": site,
            "pagesize": limit,
            "filter": "withbody",  # include body field
        }
        if tagged:
            params["tagged"] = tagged

        data, err = _http_get("https://api.stackexchange.com/2.3/search/advanced", params=params)
        if err:
            return ToolResult.fail(err)
        items = (data or {}).get("items", [])
        if not items:
            return ToolResult.fail("no results")

        out = [f"# StackExchange ({site}): {q}", ""]
        for q_item in items[:limit]:
            score = q_item.get("score", 0)
            answers = q_item.get("answer_count", 0)
            answered = "✓" if q_item.get("is_answered") else " "
            title = q_item.get("title", "")
            link = q_item.get("link", "")
            tags = ",".join(q_item.get("tags", [])[:5])
            out.append(f"  [{score:>4}↑ {answers:>2}A {answered}]  {title}")
            out.append(f"      tags: {tags}")
            out.append(f"      {link}")
        return ToolResult.ok("\n".join(out))


# Tools list — exported so registry.py can collect them
FREE_API_TOOLS = [
    HnTopTool(),
    HnItemTool(),
    WeatherTool(),
    CurrencyTool(),
    WikiTool(),
    ArxivTool(),
    RedditTool(),
    NasaApodTool(),
    CountryTool(),
    IpLookupTool(),
    CryptoPriceTool(),
    PokemonTool(),
    StackExchangeTool(),
]
