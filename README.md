# Jarscope

Browse and search JVM library source code by Maven coordinate.

Jarscope is an [MCP](https://modelcontextprotocol.io/) server that gives coding agents fast, reliable access to JVM library APIs. Instead of guessing or searching the filesystem, agents can look up classes, functions, and usage patterns directly in a library's published source code.

## Install

```
uvx jarscope
```

## Configure

### Claude Code

```sh
claude mcp add jarscope -- uvx jarscope
```

### Claude Desktop / Cursor / etc.

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

## Tools

### `jar_search`

Search a library's source code for a regex pattern. Returns matching lines with surrounding context.

```
jar_search("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.0", "class Json")
```

### `jar_read`

Read the full source of a specific file in a library.

```
jar_read("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.0", "commonMain/kotlinx/serialization/json/Json.kt")
```

### `jar_list`

List files in a library's source JAR, optionally filtered by package path.

```
jar_list("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.0", prefix="commonMain/kotlinx/serialization/json")
```

## How it works

All three tools take a Maven coordinate (`groupId:artifactId:version`), which agents can find in `build.gradle.kts`, `pom.xml`, or `gradle/libs.versions.toml`.

Jarscope resolves coordinates to source JARs by checking, in order:

1. Gradle cache (`~/.gradle/caches/`)
2. Maven local repo (`~/.m2/repository/`)
3. Maven Central (downloaded and cached locally)

JARs are read directly as ZIP files — no extraction needed. Sources JARs are preferred; javadoc JARs are used as fallback.

## License

MIT
