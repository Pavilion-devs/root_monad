"""Read-only check through the official MCP client and a real stdio subprocess."""
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[2]

async def main():
    config=json.loads((ROOT/'integrations/claude-code/mcp.json').read_text())['mcpServers']['portable-memory']
    params=StdioServerParameters(command=config['command'],args=config['args'],env={k:os.environ[k] for k in ('HOME','PATH') if k in os.environ})
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=90)) as session:
            await session.initialize();tools=await session.list_tools()
            assert {t.name for t in tools.tools}=={'memory_current','memory_propose'}
            result=await session.call_tool('memory_current',{})
            assert not result.isError
            data=result.structuredContent
            if data is None:data=json.loads(result.content[0].text)
            assert data['verification']=='current_verified'
            print(json.dumps({'passed':True,'tools':[t.name for t in tools.tools],'checkpoint':data['checkpoint'],'recordCount':len(data['records'])}))

if __name__=='__main__':asyncio.run(main())
