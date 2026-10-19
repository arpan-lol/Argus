from langchain_core.tools import StructuredTool

from .contracts import AGENT_TOOLS, TOOLS
from .routes import execute


def get_tools():
    tools = []
    for name in AGENT_TOOLS:
        schema, description = TOOLS[name]
        def bind(tool_name):
            def invoke(**arguments):
                return execute(tool_name, arguments)
            return invoke
        tools.append(StructuredTool.from_function(func=bind(name), name=name, description=description, args_schema=schema))
    return tools
