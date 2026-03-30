---
name: web_search
description: "Search the web for information and retrieve relevant results. Use this skill when you need to find current information, research topics, or gather data from online sources."
---

# Web Search Skill

## Overview

This skill enables you to search the web for information using search APIs and return relevant results.

## When to Use

- Researching current events or topics
- Finding specific information online
- Gathering data from multiple sources
- Validating information with web sources

## Usage

Search for information about a specific topic:

```
search(query="人工智能最新发展", topic="general", max_results=10)
```

## Parameters

- `query` (required): The search query string
- `topic` (optional): "general", "news", "finance", "science" etc.
- `search_depth` (optional): "basic" or "advanced"
- `max_results` (optional): Maximum number of results (default: 10)

## Returns

- List of search results with titles, URLs, and snippets
- Structured data ready for further processing
- Relevance scores for each result

## Examples

```
# Search for AI news
search("artificial intelligence news", topic="news", max_results=5)

# Financial information search
search("Tesla stock price 2026", topic="finance")

# Science research
search("quantum computing breakthrough", search_depth="advanced")
```
