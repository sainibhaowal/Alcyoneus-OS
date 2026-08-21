from fastmcp import FastMCP


mcp = FastMCP("My MCP Server")


@mcp.tool(
    description="Get the weather for a specific location",
    tags={"weather", "information"},
    exclude_args=["user_details"],
)
def get_weather(location: str, user: dict | None = None) -> dict:
    print(f"User Details: {user}")
    return {
        "location": location,
        "temperature": "22°C",
        "description": "Sunny",
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
