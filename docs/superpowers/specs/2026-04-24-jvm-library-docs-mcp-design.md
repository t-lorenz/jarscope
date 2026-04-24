# JVM Library Docs MCP Tool — MVP Design Spec

## Purpose

Give coding agents a fast, reliable way to answer questions about JVM library APIs. Replaces multi-call filesystem archaeology with 1-3 targeted MCP tool calls against library source/javadoc JARs.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python | Simple, good stdlib ZIP support, official MCP SDK |
| MCP SDK | FastMCP | Decorator-based, concise tool registration |
| Search engine | Python `re` module | Zero deps, sufficient for single-JAR searches |
| HTTP client | httpx | Clean API, async-capable |
| Cache location | platformdirs | Cross-platform cache dir handling |
| Distribution | uvx (PyPI) + Homebrew | Standard MCP distribution + broad reach |
| Structure | Flat single-module | ~5 files, MVP-appropriate |

## Tools

### `search(coordinate, query, case_insensitive?, context_lines?)`

Search library sources for a regex pattern. Returns matching lines with surrounding context.

**Parameters:**
- `coordinate: str` — Maven coordinate `groupId:artifactId:version`
- `query: str` — regex pattern
- `case_insensitive: bool = False`
- `context_lines: int = 3` — lines of context above/below each match

**Returns:** matches in `{path}:{line_number}: {line_content}` format, grouped by file. Skips binary files (null byte detection in first 512 bytes).

### `read(coordinate, path)`

Read a specific file from a library's sources.

**Parameters:**
- `coordinate: str` — Maven coordinate
- `path: str` — path within the JAR (e.g., `com/example/Foo.kt`)

**Returns:** file contents decoded as UTF-8. For javadoc JARs, returns raw HTML.

### `list_files(coordinate, prefix?)`

List files in a library's sources.

**Parameters:**
- `coordinate: str` — Maven coordinate
- `prefix: str | None = None` — optional path prefix filter (e.g., `com/example/`)

**Returns:** list of file paths within the JAR.

### Response Envelope

All tools return:

```json
{
  "status": "ok | not_found | sources_unavailable | file_not_found | invalid_coordinate | error",
  "coordinate": "org.example:lib:1.0",
  "resolved_version": "1.0",
  "jar_type": "sources | javadoc",
  "source": "gradle_cache | maven_local | maven_central",
  "data": "..."
}
```

## JAR Resolution Chain

Priority order — return first hit:

1. **Gradle cache** (`~/.gradle/caches/modules-2/files-2.1/{groupId}/{artifactId}/{version}/`)
   - Note: Gradle uses dotted `groupId` as-is (e.g., `org.jetbrains.kotlinx`), not slash-separated
   - Gradle stores JARs in hash-named subdirectories
   - Glob for `*/*-sources.jar` under the version directory
2. **Maven local repo** (`~/.m2/repository/{group/path}/{artifactId}/{version}/`)
   - Direct path lookup: `{artifactId}-{version}-sources.jar`
3. **Maven Central** (`https://repo1.maven.org/maven2/{group/path}/{artifactId}/{version}/`)
   - Fetch `{artifactId}-{version}-sources.jar`
   - On 404, try `-javadoc.jar` as fallback
   - Save to local cache on success

### Coordinate Parsing

- `groupId:artifactId:version` → split on `:`
- `groupId` dots become `/` for path construction: `org.jetbrains.kotlinx` → `org/jetbrains/kotlinx`
- Invalid format (not exactly 3 parts) → `status: "invalid_coordinate"`

### SNAPSHOT Handling

- If `version` ends with `-SNAPSHOT`: cached file mtime checked, re-fetch if older than 1 hour
- Release versions: no eviction (immutable coordinates)

## JAR Reading

All operations use `zipfile.ZipFile` — no extraction to disk:

- **list**: `ZipFile.namelist()`, filter by prefix if provided
- **read**: `ZipFile.read(path)`, decode UTF-8
- **search**: iterate entries, read each text file, apply regex, collect matches with context lines

Binary file detection: check first 512 bytes for null bytes. Skip binary files during search.

## Download Cache

Location: `platformdirs.user_cache_dir("jvm-mcp")`

- Layout mirrors Maven repo: `{cache_dir}/{group/path}/{artifactId}/{version}/{filename}`
- Write to temp file, atomic rename on success (no partial files)
- Release versions: cached forever
- SNAPSHOT versions: re-fetch if mtime > 1 hour

## Project Structure

```
jvm-mcp/
  pyproject.toml
  src/
    jvm_mcp/
      __init__.py
      server.py       # FastMCP server, tool handlers, entry point
      resolver.py     # JAR resolution: Gradle → Maven local → Maven Central
      jar.py          # ZIP reading: list, read, search operations
      cache.py        # Download cache management
  tests/
    test_resolver.py
    test_jar.py
    test_search.py
```

## Dependencies

- `mcp[cli]` — FastMCP + MCP protocol
- `httpx` — HTTP client for Maven Central
- `platformdirs` — cross-platform cache directory

Python >= 3.11.

## Packaging & Distribution

### PyPI / uvx

`pyproject.toml` entry point:
```toml
[project.scripts]
jvm-mcp = "jvm_mcp.server:main"
```

Claude configuration:
```json
{
  "mcpServers": {
    "jvm-mcp": {
      "command": "uvx",
      "args": ["jvm-mcp"]
    }
  }
}
```

### Homebrew

Homebrew tap with formula that installs via pipx into isolated environment.

## Error Handling

All errors are structured responses — no exceptions leak to the agent:

| Condition | Status | Notes |
|-----------|--------|-------|
| Bad coordinate format | `invalid_coordinate` | Message explains expected format |
| JAR not found anywhere | `not_found` | Lists locations tried |
| No sources, javadoc exists | Uses javadoc | `jar_type: "javadoc"` in response |
| Neither sources nor javadoc | `sources_unavailable` | |
| File not in JAR | `file_not_found` | Suggests similar paths if possible |
| Network error | `error` | Includes error details |

## Scope Boundaries

### In MVP
- Three tools: search, read, list_files
- Gradle cache, Maven local, Maven Central resolution
- Sources JAR preferred, javadoc JAR fallback
- Regex search with context lines
- Local download cache with SNAPSHOT TTL
- uvx + Homebrew distribution

### Explicitly NOT in MVP
- No KDoc/Javadoc parsing into structured form
- No HTML-to-markdown conversion
- No curated `get_docs` view
- No semantic search, symbol indexing, or cross-references
- No LLM-generated overviews
- No version diffs or cross-library comparison
- No automatic coordinate resolution from project context
- No telemetry

## Validation

Manual test against a known library (e.g., `org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.0`):

1. `list_files` — verify file tree returned
2. `search` with a known API name — verify matching lines with context
3. `read` a specific source file — verify full contents returned
4. Test resolution from Maven Central (clear local cache)
5. Test error cases: bad coordinate, missing library, missing file within JAR
