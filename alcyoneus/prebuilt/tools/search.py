"""Multi-provider web search tools for Alcyoneus OS agents.

Supports: Google (Gemini), Bing, Brave, DuckDuckGo, SerpAPI, Tavily, Exa.
Includes result ranking, citation extraction, and safe-search toggle.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

import aiohttp

from alcyoneus.utils.decorators import tool


_DEFAULT_MODEL = "gemini-2.5-flash"
_DEFAULT_MAX_CHARS = 20_000
_MAX_RESULTS = 20


def _to_plain(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_to_plain(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_plain(value.model_dump())
    if hasattr(value, "to_json_dict"):
        return _to_plain(value.to_json_dict())
    return str(value)


def _response_payload(response: Any, max_chars: int) -> dict[str, Any]:
    text = getattr(response, "text", "") or ""
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    grounding_metadata = None
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        grounding_metadata = _to_plain(getattr(candidates[0], "grounding_metadata", None))

    return {
        "content": text,
        "grounding_metadata": grounding_metadata,
        "truncated": truncated,
    }


def _google_web_search_sync(query: str, model: str, max_chars: int) -> dict[str, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {"error": "google-genai required: pip install alcyoneus[google-genai]"}

    client = genai.Client()
    response = client.models.generate_content(
        model=model,
        contents=query,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    return _response_payload(response, max_chars)


def _vertex_ai_search_sync(
    query: str, datastore: str, model: str, max_chars: int
) -> dict[str, Any]:
    if not datastore:
        return {"error": "datastore is required"}
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {"error": "google-genai required: pip install alcyoneus[google-genai]"}

    client = genai.Client(http_options=types.HttpOptions(api_version="v1"))
    response = client.models.generate_content(
        model=model,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    retrieval=types.Retrieval(
                        vertex_ai_search=types.VertexAISearch(datastore=datastore),
                    )
                )
            ],
        ),
    )
    return _response_payload(response, max_chars)


async def _http_get_json(url: str, headers: dict | None = None, params: dict | None = None) -> dict:
    async with (
        aiohttp.ClientSession() as sess,
        sess.get(
            url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp,
    ):
        return await resp.json()


def _rank_results(results: list[dict], query: str) -> list[dict]:
    """Simple relevance ranking: boost exact phrase matches, penalize short snippets."""
    q_terms = set(re.findall(r"\w+", query.lower()))
    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        score = sum(1 for t in q_terms if t in text)
        r["_relevance"] = score + len(r.get("snippet", "")) * 0.01
    results.sort(key=lambda x: x.get("_relevance", 0), reverse=True)
    return results


def _extract_citations(results: list[dict]) -> list[dict]:
    """Extract citation info: url, title, snippet."""
    return [
        {"url": r.get("url"), "title": r.get("title"), "snippet": r.get("snippet", "")[:200]}
        for r in results
    ]


async def _bing_search(query: str, max_results: int, safe_search: bool) -> dict:
    key = os.getenv("BING_API_KEY")
    if not key:
        return {"error": "BING_API_KEY not set"}
    headers = {"Ocp-Apim-Subscription-Key": key}
    params = {
        "q": query,
        "count": min(max_results, 50),
        "safeSearch": "strict" if safe_search else "moderate",
        "textFormat": "raw",
    }
    data = await _http_get_json("https://api.bing.microsoft.com/v7.0/search", headers, params)
    results = []
    for v in data.get("webPages", {}).get("value", []):
        results.append(
            {"title": v.get("name"), "url": v.get("url"), "snippet": v.get("snippet", "")}
        )
    return {"results": _rank_results(results, query), "citations": _extract_citations(results)}


async def _brave_search(query: str, max_results: int, safe_search: bool) -> dict:
    key = os.getenv("BRAVE_API_KEY")
    if not key:
        return {"error": "BRAVE_API_KEY not set"}
    headers = {"Accept": "application/json", "X-Subscription-Token": key}
    params = {
        "q": query,
        "count": min(max_results, 20),
        "safesearch": "strict" if safe_search else "moderate",
    }
    data = await _http_get_json("https://api.search.brave.com/res/v1/web/search", headers, params)
    results = []
    for v in data.get("web", {}).get("results", []):
        results.append(
            {"title": v.get("title"), "url": v.get("url"), "snippet": v.get("description", "")}
        )
    return {"results": _rank_results(results, query), "citations": _extract_citations(results)}


async def _duckduckgo_search(query: str, max_results: int, safe_search: bool) -> dict:
    # DuckDuckGo HTML scrape (no official API)
    import urllib.parse

    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    params = {"kl": "us-en", "safesearch": "1" if safe_search else "0"}
    async with aiohttp.ClientSession() as sess:
        async with sess.post(url, data=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            html = await resp.text()
    results = []
    for m in re.finditer(r'class="result__snippet".*?>(.*?)</a>', html, re.DOTALL):
        snippet = re.sub(r"<[^>]+>", "", m.group(1))[:200]
        results.append({"title": "", "url": "", "snippet": snippet})
        if len(results) >= max_results:
            break
    return {"results": _rank_results(results, query), "citations": _extract_citations(results)}


async def _serpapi_search(query: str, max_results: int, safe_search: bool) -> dict:
    key = os.getenv("SERPAPI_KEY")
    if not key:
        return {"error": "SERPAPI_KEY not set"}
    params = {
        "q": query,
        "num": min(max_results, 100),
        "safe": "active" if safe_search else "off",
        "api_key": key,
    }
    data = await _http_get_json("https://serpapi.com/search", params=params)
    results = []
    for v in data.get("organic_results", []):
        results.append(
            {"title": v.get("title"), "url": v.get("link"), "snippet": v.get("snippet", "")}
        )
    return {"results": _rank_results(results, query), "citations": _extract_citations(results)}


async def _tavily_search(query: str, max_results: int, safe_search: bool) -> dict:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return {"error": "TAVILY_API_KEY not set"}
    async with (
        aiohttp.ClientSession() as sess,
        sess.post(
            "https://api.tavily.com/search",
            json={
                "api_key": key,
                "query": query,
                "max_results": max_results,
                "safe_search": safe_search,
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp,
    ):
        data = await resp.json()
    results = []
    for v in data.get("results", []):
        results.append(
            {"title": v.get("title"), "url": v.get("url"), "snippet": v.get("content", "")[:200]}
        )
    return {"results": _rank_results(results, query), "citations": _extract_citations(results)}


async def _exa_search(query: str, max_results: int, safe_search: bool) -> dict:
    key = os.getenv("EXA_API_KEY")
    if not key:
        return {"error": "EXA_API_KEY not set"}
    async with (
        aiohttp.ClientSession() as sess,
        sess.post(
            "https://api.exa.ai/search",
            json={"query": query, "num_results": max_results, "use_autoprompt": True},
            headers={"x-api-key": key, "Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp,
    ):
        data = await resp.json()
    results = []
    for v in data.get("results", []):
        results.append(
            {"title": v.get("title"), "url": v.get("url"), "snippet": v.get("text", "")[:200]}
        )
    return {"results": _rank_results(results, query), "citations": _extract_citations(results)}


@tool(
    name="google_web_search",
    description="Search the public web with Gemini Google Search grounding.",
    tags=["web", "search", "google"],
    capabilities=["network_access"],
)
async def google_web_search(
    query: str, model: str = _DEFAULT_MODEL, max_chars: int = _DEFAULT_MAX_CHARS
) -> str:
    if not query:
        return json.dumps({"error": "query is required"})
    safe_max = max(1, min(int(max_chars), _DEFAULT_MAX_CHARS))
    result = await asyncio.to_thread(_google_web_search_sync, query, model, safe_max)
    return json.dumps(result)


@tool(
    name="vertex_ai_search",
    description="Search a Vertex AI Search datastore with Gemini grounding.",
    tags=["search", "google", "vertex_ai"],
    capabilities=["network_access"],
)
async def vertex_ai_search(
    query: str,
    datastore: str,
    model: str = _DEFAULT_MODEL,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    if not query:
        return json.dumps({"error": "query is required"})
    safe_max = max(1, min(int(max_chars), _DEFAULT_MAX_CHARS))
    result = await asyncio.to_thread(_vertex_ai_search_sync, query, datastore, model, safe_max)
    return json.dumps(result)


@tool(
    name="bing_search",
    description="Search the web via Microsoft Bing API with ranking and citations.",
    tags=["web", "search", "bing"],
    capabilities=["network_access"],
)
async def bing_search(query: str, max_results: int = 10, safe_search: bool = True) -> str:
    if not query:
        return json.dumps({"error": "query is required"})
    result = await _bing_search(query, min(max_results, _MAX_RESULTS), safe_search)
    return json.dumps(result)


@tool(
    name="brave_search",
    description="Search the web via Brave Search API with ranking and citations.",
    tags=["web", "search", "brave"],
    capabilities=["network_access"],
)
async def brave_search(query: str, max_results: int = 10, safe_search: bool = True) -> str:
    if not query:
        return json.dumps({"error": "query is required"})
    result = await _brave_search(query, min(max_results, _MAX_RESULTS), safe_search)
    return json.dumps(result)


@tool(
    name="duckduckgo_search",
    description="Search the web via DuckDuckGo (HTML scrape) with ranking.",
    tags=["web", "search", "duckduckgo"],
    capabilities=["network_access"],
)
async def duckduckgo_search(query: str, max_results: int = 10, safe_search: bool = True) -> str:
    if not query:
        return json.dumps({"error": "query is required"})
    result = await _duckduckgo_search(query, min(max_results, _MAX_RESULTS), safe_search)
    return json.dumps(result)


@tool(
    name="serpapi_search",
    description="Search the web via SerpAPI with ranking and citations.",
    tags=["web", "search", "serpapi"],
    capabilities=["network_access"],
)
async def serpapi_search(query: str, max_results: int = 10, safe_search: bool = True) -> str:
    if not query:
        return json.dumps({"error": "query is required"})
    result = await _serpapi_search(query, min(max_results, _MAX_RESULTS), safe_search)
    return json.dumps(result)


@tool(
    name="tavily_search",
    description="Search the web via Tavily API with ranking and citations.",
    tags=["web", "search", "tavily"],
    capabilities=["network_access"],
)
async def tavily_search(query: str, max_results: int = 10, safe_search: bool = True) -> str:
    if not query:
        return json.dumps({"error": "query is required"})
    result = await _tavily_search(query, min(max_results, _MAX_RESULTS), safe_search)
    return json.dumps(result)


@tool(
    name="exa_search",
    description="Search the web via Exa AI API with ranking and citations.",
    tags=["web", "search", "exa"],
    capabilities=["network_access"],
)
async def exa_search(query: str, max_results: int = 10, safe_search: bool = True) -> str:
    if not query:
        return json.dumps({"error": "query is required"})
    result = await _exa_search(query, min(max_results, _MAX_RESULTS), safe_search)
    return json.dumps(result)


@tool(
    name="multi_search",
    description="Run multiple search providers and merge results with deduplication.",
    tags=["web", "search", "multi"],
    capabilities=["network_access"],
)
async def multi_search(
    query: str,
    providers: list[str] | None = None,
    max_results: int = 10,
    safe_search: bool = True,
) -> str:
    """Aggregate results from multiple search providers."""
    if not query:
        return json.dumps({"error": "query is required"})
    if providers is None:
        providers = ["google", "bing", "brave"]
    provider_map = {
        "google": google_web_search,
        "bing": bing_search,
        "brave": brave_search,
        "duckduckgo": duckduckgo_search,
        "serpapi": serpapi_search,
        "tavily": tavily_search,
        "exa": exa_search,
    }
    all_results = []
    seen_urls = set()
    for p in providers:
        if p not in provider_map:
            continue
        try:
            raw = await provider_map[p](query, max_results, safe_search)
            data = json.loads(raw)
            for r in data.get("results", []):
                url = r.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)
        except Exception:  # noqa: S110
            pass
    merged = {
        "results": _rank_results(all_results, query)[:max_results],
        "citations": _extract_citations(all_results[:max_results]),
    }
    return json.dumps(merged)
