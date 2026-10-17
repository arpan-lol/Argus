from langchain_core.tools import StructuredTool

from .contracts import TOOLS
from .routes import execute


def get_tools():
    tools = []
    for name, (schema, description) in TOOLS.items():
        def bind(tool_name):
            def invoke(**arguments):
                return execute(tool_name, arguments)
            return invoke
        tools.append(StructuredTool.from_function(func=bind(name), name=name, description=description, args_schema=schema))
    return tools
