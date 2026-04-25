# Jarscope

**Give your coding agent direct access to any JVM library's source code.**

When agents work with Kotlin or Java projects, they constantly need to check library APIs — how a function works, what parameters it takes, what exceptions it throws. Without Jarscope, they guess, hallucinate, or waste dozens of tool calls digging through your filesystem. With Jarscope, they look it up in 1-3 calls.

## Quick start

### Claude Code

```sh
claude mcp add jarscope -- uvx jarscope
```

That's it. Your agent can now search, read, and browse the source code of any library in your project's dependencies.

### Codex

```sh
codex mcp add jarscope -- uvx jarscope
```

### Cursor / Windsurf / Claude Desktop

Add to your MCP config:

```json
{
  "mcpServers": {
    "jarscope": {
      "command": "uvx",
      "args": ["jarscope"]
    }
  }
}
```

Works with any MCP-compatible client.

## What your agent gets

Three tools. The agent supplies a Maven coordinate (`groupId:artifactId:version`) from your `build.gradle.kts`, `pom.xml`, or `gradle/libs.versions.toml`.

**`jar_search`** — Search a library's source code for a pattern. Returns matching lines with context, like ripgrep output.

**`jar_read`** — Read a specific source file in full.

**`jar_list`** — Browse the file tree of a library to discover what's inside.

## How it works

Jarscope resolves Maven coordinates to source JARs by checking:

1. Your Gradle cache (`~/.gradle/caches/`)
2. Your Maven local repo (`~/.m2/repository/`)
3. Maven Central (downloaded and cached locally)

If you've built your project before, the JAR is probably already on your machine. If not, Jarscope fetches it. Sources JARs are preferred; javadoc JARs are used as fallback.

JARs are read directly as ZIP files — nothing is extracted to disk.

## Supported libraries

- Kotlin libraries with sources JARs — full support
- Java libraries with sources JARs — full support
- Libraries with only javadoc JARs — returns HTML, agent parses
- Libraries with no published sources — clear error message

## License

MIT
